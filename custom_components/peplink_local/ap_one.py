"""Peplink AP One support, read over SNMPv2c with the Pepwave enterprise MIB.

AP One firmware has no local REST API, so an AP One entry polls a few apSystem
and ap-wlan-mib values plus the wireless client table instead.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from pysnmp.hlapi.v1arch.asyncio import (
    CommunityData,
    ObjectIdentity,
    ObjectType,
    SnmpDispatcher,
    UdpTransportTarget,
    get_cmd,
    walk_cmd,
)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.variance import ignore_variance

from .const import (
    CONF_COMMUNITY,
    CONF_POLL_FREQUENCY,
    DEFAULT_COMMUNITY,
    DEFAULT_SNMP_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

AP_ONE_PLATFORMS: list[Platform] = [Platform.SENSOR]
DEFAULT_AP_ONE_POLL_FREQUENCY = 30  # seconds

PEPWAVE = "1.3.6.1.4.1.27662.200.1.1"
OID_SERIAL = f"{PEPWAVE}.1.1.1.1.0"
OID_MAC = f"{PEPWAVE}.1.1.1.2.0"
OID_FIRMWARE = f"{PEPWAVE}.1.1.1.3.0"
OID_UPTIME = f"{PEPWAVE}.1.1.1.5.0"
OID_HOSTNAME = f"{PEPWAVE}.1.2.1.1.0"
OID_LAN_IP = f"{PEPWAVE}.2.1.1.2.0"
OID_SSID = f"{PEPWAVE}.4.1.1.1.2.0"
OID_RADIO_CHANNELS = (f"{PEPWAVE}.3.1.1.1.4.0", f"{PEPWAVE}.3.1.1.1.4.1")
OID_CLIENT_TABLE = f"{PEPWAVE}.6.1.1.1"
CLIENT_COLUMNS = {"2": "mac", "3": "ip", "4": "name", "7": "signal", "10": "band"}


def _plain(value: Any) -> Any:
    """Convert a PySNMP value to a plain Python value; None for missing objects."""
    kind = type(value).__name__
    if kind in ("NoSuchObject", "NoSuchInstance", "EndOfMibView", "Null"):
        return None
    if kind == "IpAddress":
        octets = bytes(value.asOctets())
        return ".".join(str(b) for b in octets) if len(octets) == 4 else None
    if kind in ("Integer", "Integer32", "Unsigned32", "Gauge32", "Counter32", "Counter64", "TimeTicks"):
        return int(value)
    if kind == "OctetString":
        octets = bytes(value.asOctets())
        try:
            text = octets.decode("utf-8").strip("\x00").strip()
        except UnicodeDecodeError:
            return octets.hex()
        return text if text.isprintable() else octets.hex()
    return str(value)


def _mac(value: Any) -> str | None:
    """Format a MAC address held as six raw octets, hex text or 0x-prefixed hex."""
    if value is None:
        return None
    if type(value).__name__ == "OctetString" and len(bytes(value.asOctets())) == 6:
        return ":".join(f"{b:02X}" for b in bytes(value.asOctets()))
    raw = "".join(c for c in str(_plain(value) or "").removeprefix("0x") if c in "0123456789abcdefABCDEF")
    return ":".join(raw[i:i + 2].upper() for i in range(0, 12, 2)) if len(raw) >= 12 else None


def _uptime_seconds(value: Any) -> int | None:
    """apSystemUptime as seconds (TimeTicks count hundredths of a second)."""
    if value is None or type(value).__name__ in ("NoSuchObject", "NoSuchInstance"):
        return None
    if type(value).__name__ == "TimeTicks":
        return int(value) // 100
    plain = _plain(value)
    return plain if isinstance(plain, int) else None


class PeplinkAPOneSNMP:
    """Minimal SNMPv2c reader for one AP One."""

    def __init__(self, host: str, community: str, port: int = DEFAULT_SNMP_PORT) -> None:
        """Initialize the reader."""
        self.host = host
        self._auth = CommunityData(community, mpModel=1)
        self._port = port
        self._dispatcher = SnmpDispatcher()
        self._transport: UdpTransportTarget | None = None

    async def _target(self) -> UdpTransportTarget:
        if self._transport is None:
            self._transport = await UdpTransportTarget.create((self.host, self._port), timeout=3, retries=1)
        return self._transport

    async def get(self, oids: list[str]) -> dict[str, Any]:
        """GET several OIDs; return raw PySNMP values keyed by OID."""
        error, status, _index, bindings = await get_cmd(
            self._dispatcher,
            self._auth,
            await self._target(),
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            lookupMib=False,
        )
        if error:
            raise UpdateFailed(f"SNMP GET to {self.host} failed: {error}")
        if status:
            raise UpdateFailed(f"SNMP GET to {self.host} failed: {status.prettyPrint()}")
        return {oids[i]: value for i, (_oid, value) in enumerate(bindings)}

    async def walk(self, base_oid: str) -> list[tuple[str, Any]]:
        """Walk one subtree; return (OID, raw value) pairs."""
        prefix = base_oid + "."
        rows: list[tuple[str, Any]] = []
        async for error, status, _index, bindings in walk_cmd(
            self._dispatcher,
            self._auth,
            await self._target(),
            ObjectType(ObjectIdentity(base_oid)),
            lookupMib=False,
            lexicographicMode=False,
        ):
            if error:
                raise UpdateFailed(f"SNMP walk of {self.host} failed: {error}")
            if status:
                raise UpdateFailed(f"SNMP walk of {self.host} failed: {status.prettyPrint()}")
            for oid, value in bindings:
                oid_str = str(oid)
                if not oid_str.startswith(prefix):
                    return rows
                rows.append((oid_str, value))
        return rows

    async def read(self) -> dict[str, Any]:
        """Read device, Wi-Fi and client data."""
        values = await self.get(
            [OID_SERIAL, OID_MAC, OID_FIRMWARE, OID_UPTIME, OID_HOSTNAME, OID_LAN_IP, OID_SSID, *OID_RADIO_CHANNELS]
        )
        clients: dict[str, dict[str, Any]] = {}
        for oid, value in await self.walk(OID_CLIENT_TABLE):
            column, _, index = oid[len(OID_CLIENT_TABLE) + 1:].partition(".")
            field = CLIENT_COLUMNS.get(column)
            if not field or not index:
                continue
            clients.setdefault(index, {})[field] = _mac(value) if field == "mac" else _plain(value)
        return {
            "device": {
                "serial_number": _plain(values[OID_SERIAL]),
                "mac": _mac(values[OID_MAC]),
                "firmware": _plain(values[OID_FIRMWARE]),
                "uptime": _uptime_seconds(values[OID_UPTIME]),
                "hostname": _plain(values[OID_HOSTNAME]),
                "lan_ip": _plain(values[OID_LAN_IP]),
            },
            "wlan": {
                "ssid": _plain(values[OID_SSID]),
                "channels": [_plain(values[oid]) for oid in OID_RADIO_CHANNELS],
            },
            "clients": [c for c in clients.values() if c.get("mac") or c.get("ip")],
        }

    def close(self) -> None:
        """Release the SNMP socket."""
        dispatcher = getattr(self._dispatcher, "transport_dispatcher", None)
        if dispatcher is not None:
            dispatcher.close_dispatcher()


async def async_probe_ap_one(host: str, community: str) -> dict[str, Any]:
    """Read an AP One once (config flow validation); raise if it does not answer."""
    reader = PeplinkAPOneSNMP(host, community)
    try:
        data = await reader.read()
    finally:
        reader.close()
    if not data["device"].get("firmware"):
        raise UpdateFailed(f"{host} answered SNMP but returned no AP One firmware")
    return data


class PeplinkAPOneCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls one AP One over SNMP."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Peplink AP One {entry.data[CONF_HOST]}",
            update_interval=datetime.timedelta(
                seconds=entry.data.get(CONF_POLL_FREQUENCY, DEFAULT_AP_ONE_POLL_FREQUENCY)
            ),
        )
        self.config_entry = entry
        self.snmp = PeplinkAPOneSNMP(entry.data[CONF_HOST], entry.data.get(CONF_COMMUNITY, DEFAULT_COMMUNITY))

    async def _async_update_data(self) -> dict[str, Any]:
        """Read the AP."""
        try:
            return await self.snmp.read()
        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(f"SNMP read of {self.snmp.host} failed: {err}") from err


async def async_setup_ap_one_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an AP One entry."""
    coordinator = PeplinkAPOneCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        coordinator.snmp.close()
        raise ConfigEntryNotReady(f"AP One {entry.data[CONF_HOST]} did not answer SNMP: {err}") from err

    device = coordinator.data["device"]
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        connections={(dr.CONNECTION_NETWORK_MAC, device["mac"].lower())} if device.get("mac") else set(),
        name=device.get("hostname") or f"AP One ({entry.data[CONF_HOST]})",
        manufacturer="Peplink",
        model="AP One",
        serial_number=device.get("serial_number"),
        sw_version=device.get("firmware"),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"coordinator": coordinator, "api": None, "kind": "ap_one"}
    await hass.config_entries.async_forward_entry_setups(entry, AP_ONE_PLATFORMS)
    return True


async def async_unload_ap_one_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an AP One entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, AP_ONE_PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)["coordinator"].snmp.close()
    return unload_ok


ap_one_uptime_to_stable_datetime = ignore_variance(
    lambda value: dt_util.utcnow() - datetime.timedelta(seconds=value),
    datetime.timedelta(minutes=1),
)


class PeplinkAPOneSensor(CoordinatorEntity, SensorEntity):
    """One value read from an AP One."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PeplinkAPOneCoordinator, key: str, name: str, value_fn, **attrs: Any) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._value_fn = value_fn
        self._attrs_fn = attrs.pop("attributes_fn", None)
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_ap_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.config_entry.entry_id)})
        for attr, value in attrs.items():
            setattr(self, f"_attr_{attr}", value)

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self._value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        return self._attrs_fn(self.coordinator.data or {}) if self._attrs_fn else None


def ap_one_sensor_entities(coordinator: PeplinkAPOneCoordinator) -> list[SensorEntity]:
    """Create the AP One sensors."""
    entities: list[SensorEntity] = [
        PeplinkAPOneSensor(
            coordinator, "clients", "Wi-Fi Clients",
            lambda d: len(d.get("clients", [])),
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:account-multiple",
            attributes_fn=lambda d: {"clients": d.get("clients", [])[:50]},
        ),
        PeplinkAPOneSensor(
            coordinator, "ssid", "SSID",
            lambda d: d.get("wlan", {}).get("ssid"),
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:wifi",
        ),
        PeplinkAPOneSensor(
            coordinator, "firmware", "Firmware Version",
            lambda d: d.get("device", {}).get("firmware"),
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:package-variant-closed",
        ),
        PeplinkAPOneSensor(
            coordinator, "last_restart", "Last Restart",
            lambda d: (
                ap_one_uptime_to_stable_datetime(d["device"]["uptime"])
                if d.get("device", {}).get("uptime") is not None
                else None
            ),
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:clock-start",
        ),
    ]
    for radio, channel in enumerate((coordinator.data or {}).get("wlan", {}).get("channels", []), 1):
        if channel:
            entities.append(
                PeplinkAPOneSensor(
                    coordinator, f"radio_{radio}_channel", f"Radio {radio} Channel",
                    lambda d, i=radio - 1: (d.get("wlan", {}).get("channels") or [None] * 2)[i],
                    entity_category=EntityCategory.DIAGNOSTIC,
                    icon="mdi:wifi-settings",
                )
            )
    return entities
