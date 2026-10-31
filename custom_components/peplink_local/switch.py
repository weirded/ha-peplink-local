"""Switch platform for Peplink Local: access point and PoE (admin login only)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN
from .entity import async_send_command, router_device_info

_LOGGER = logging.getLogger(__name__)


def _poe_port(data: dict[str, Any] | None, port_id: str) -> dict[str, Any] | None:
    """Return the PoE block of a LAN port that supports PoE, or None."""
    port = ((data or {}).get("port_status") or {}).get("lan", {}).get(port_id)
    if not isinstance(port, dict):
        return None
    poe = port.get("poe")
    if not isinstance(poe, dict) or "enable" not in poe:
        return None
    if (poe.get("status") or {}).get("value") == "notavailable":
        return None
    return poe


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Peplink switches; none without an admin login."""
    coordinator: PeplinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if not coordinator.is_admin:
        return

    data = coordinator.data or {}
    entities: list[SwitchEntity] = []

    if "status" in (data.get("ap_status") or {}):
        entities.append(PeplinkAccessPointSwitch(coordinator))

    lan_ports = (data.get("port_status") or {}).get("lan", {})
    for port_id in lan_ports.get("order", []):
        if _poe_port(data, str(port_id)) is not None:
            entities.append(PeplinkPoESwitch(coordinator, str(port_id)))

    async_add_entities(entities)


class PeplinkAccessPointSwitch(CoordinatorEntity, SwitchEntity):
    """Turns the router's built-in Wi-Fi access point on or off (POST cmd.ap)."""

    _attr_has_entity_name = True
    _attr_name = "Wi-Fi Access Point"
    _attr_icon = "mdi:access-point"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PeplinkDataUpdateCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_access_point_switch"
        self._attr_device_info = router_device_info(coordinator)

    @property
    def available(self) -> bool:
        """Return True while the router reports its access point."""
        return super().available and "status" in ((self.coordinator.data or {}).get("ap_status") or {})

    @property
    def is_on(self) -> bool | None:
        """Return True if the access point is on."""
        status = ((self.coordinator.data or {}).get("ap_status") or {}).get("status")
        return None if status is None else status == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the access point on."""
        await async_send_command(self.coordinator, "cmd.ap", {"enable": True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the access point off."""
        await async_send_command(self.coordinator, "cmd.ap", {"enable": False})


class PeplinkPoESwitch(CoordinatorEntity, SwitchEntity):
    """Turns PoE on a LAN port on or off (POST cmd.port.poe.enable / disable)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:ethernet"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PeplinkDataUpdateCoordinator, port_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._port_id = port_id
        self._attr_name = f"LAN Port {port_id} PoE"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_lan_port_{port_id}_poe"
        self._attr_device_info = router_device_info(coordinator)

    @property
    def available(self) -> bool:
        """Return True while the port still reports PoE."""
        return super().available and _poe_port(self.coordinator.data, self._port_id) is not None

    @property
    def is_on(self) -> bool | None:
        """Return True if PoE is enabled on the port."""
        poe = _poe_port(self.coordinator.data, self._port_id)
        return None if poe is None else poe.get("enable") is True

    async def _async_set_poe(self, enable: bool) -> None:
        """Send the PoE command, then check the device applied it."""
        # SD switches require port objects ("Mandatory - id in port[0]"); routers accept them too
        await async_send_command(
            self.coordinator,
            "cmd.port.poe.enable" if enable else "cmd.port.poe.disable",
            {"port": [{"id": int(self._port_id)}]},
        )
        poe = _poe_port(self.coordinator.data, self._port_id)
        if poe is not None and poe.get("enable") is not enable:
            raise HomeAssistantError(
                f"Port {self._port_id} PoE is still {'on' if poe.get('enable') else 'off'}: the device "
                "accepted the command but did not apply it. A switch managed by a router's Switch "
                "Controller keeps the controller's PoE setting; change it there."
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable PoE on the port."""
        await self._async_set_poe(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable PoE on the port."""
        await self._async_set_poe(False)
