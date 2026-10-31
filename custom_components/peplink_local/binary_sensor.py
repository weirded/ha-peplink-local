"""Binary sensor platform for Peplink Local integration."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class PeplinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Peplink binary sensor entities."""

    value_fn: Callable[[dict], Any] | None = None
    icon: str | None = None
    attributes_fn: Callable[[dict], dict[str, Any]] | None = None


BINARY_SENSOR_TYPES: tuple[PeplinkBinarySensorEntityDescription, ...] = (
    PeplinkBinarySensorEntityDescription(
        key="connection_status",
        translation_key=None,
        name="Connection Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda x: x.get("message", "").startswith("Connected"),
        icon="mdi:network",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Peplink binary sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = []
    
    # Get the WAN status data
    wan_status = coordinator.data.get("wan_status", {})
    wan_connections = wan_status.get("connection", [])
    
    # Add binary sensors for each WAN connection
    for connection in wan_connections:
        wan_id = connection.get("id", "")
        wan_name = connection.get("name", f"WAN {wan_id}")
        
        # Skip disabled WANs
        if connection.get("enable") is False:
            continue
            
        # Use the device name from API if available, otherwise fallback to IP
        device_name = coordinator.device_name or f"Peplink {coordinator.host}"
            
        # Create device info for this WAN
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_wan{wan_id}")},
            manufacturer="Peplink",
            model="WAN Connection",
            name=f"{device_name} WAN{wan_id}",
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )
        
        # Add all binary sensors
        for description in BINARY_SENSOR_TYPES:
            entities.append(
                PeplinkWANBinarySensor(
                    coordinator=coordinator,
                    description=description,
                    sensor_data=connection,
                    device_info=device_info,
                    wan_id=wan_id,
                )
            )

    entities.extend(_router_status_entities(coordinator))

    async_add_entities(entities)


def _pepvpn_profile(data: dict, profile_id: str) -> dict | None:
    """Return a SpeedFusion profile with its peers attached, or None if it is gone."""
    status = data.get("pepvpn_status") or {}
    profile = (status.get("profile") or {}).get(profile_id)
    if not isinstance(profile, dict):
        return None
    peers = [peer for peer in status.get("peer") or [] if str(peer.get("profileId")) == profile_id]
    return {**profile, "peers": peers}


def _port(data: dict, side: str, port_id: str) -> dict | None:
    """Return one LAN or WAN Ethernet port, or None if it is gone."""
    port = ((data.get("port_status") or {}).get(side) or {}).get(port_id)
    return port if isinstance(port, dict) else None


def _router_status_entities(coordinator: PeplinkDataUpdateCoordinator) -> list[BinarySensorEntity]:
    """Create SpeedFusion, access point and port binary sensors the router has data for."""
    data = coordinator.data or {}
    entities: list[BinarySensorEntity] = []

    # One sensor per SpeedFusion (PepVPN) profile
    profiles = (data.get("pepvpn_status") or {}).get("profile") or {}
    for profile_id in profiles.get("order", []):
        profile_id = str(profile_id)
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            continue
        entities.append(
            PeplinkRouterBinarySensor(
                coordinator=coordinator,
                description=PeplinkBinarySensorEntityDescription(
                    key=f"pepvpn_{profile_id}",
                    name=f"SpeedFusion {profile.get('name') or profile_id}",
                    device_class=BinarySensorDeviceClass.CONNECTIVITY,
                    value_fn=lambda x: x.get("status") == "CONNECTED",
                    attributes_fn=lambda x: {
                        "status": x.get("status"),
                        "type": x.get("type"),
                        "peer_count": x.get("peerCount"),
                        "peers": [
                            {"name": peer.get("name"), "status": peer.get("status")}
                            for peer in x.get("peers", [])
                        ],
                    },
                    icon="mdi:vpn",
                ),
                item_fn=lambda d, pid=profile_id: _pepvpn_profile(d, pid),
            )
        )

    # Built-in Wi-Fi access point
    if "status" in (data.get("ap_status") or {}):
        entities.append(
            PeplinkRouterBinarySensor(
                coordinator=coordinator,
                description=PeplinkBinarySensorEntityDescription(
                    key="access_point",
                    name="Wi-Fi Access Point",
                    value_fn=lambda x: x.get("status") == "on",
                    attributes_fn=lambda x: {
                        "ssids": [ssid.get("ssid") for ssid in x.get("ssid") or []],
                    },
                    icon="mdi:access-point",
                ),
                item_fn=lambda d: d.get("ap_status") or None,
            )
        )

    # Link state of each LAN and WAN Ethernet port
    for side, label in (("lan", "LAN"), ("wan", "WAN")):
        ports = (data.get("port_status") or {}).get(side) or {}
        for port_id in ports.get("order", []):
            port_id = str(port_id)
            if not isinstance(ports.get(port_id), dict):
                continue
            entities.append(
                PeplinkRouterBinarySensor(
                    coordinator=coordinator,
                    description=PeplinkBinarySensorEntityDescription(
                        key=f"{side}_port_{port_id}_link",
                        name=f"{label} Port {port_id} Link",
                        device_class=BinarySensorDeviceClass.CONNECTIVITY,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        value_fn=lambda x: x.get("linkUp") is True,
                        attributes_fn=lambda x: {
                            "port_name": x.get("name"),
                            "enabled": x.get("enable"),
                            "speed": x.get("speed"),
                        },
                        icon="mdi:ethernet",
                    ),
                    item_fn=lambda d, s=side, p=port_id: _port(d, s, p),
                )
            )

    return entities


class PeplinkWANBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Implementation of a Peplink WAN binary sensor."""

    entity_description: PeplinkBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeplinkDataUpdateCoordinator,
        description: PeplinkBinarySensorEntityDescription,
        sensor_data: dict[str, Any],
        device_info: DeviceInfo,
        wan_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self.entity_description = description
        self._initial_sensor_data = sensor_data  # Keep reference to initial data as fallback
        self._wan_id = wan_id  # Store WAN ID to find the right data in updates
        self._attr_unique_id = f"{coordinator.host}_wan{wan_id}_{description.key}_binary_{coordinator.config_entry.entry_id}"
        self._attr_device_info = device_info
        
        # Set custom icon if provided
        if description.icon:
            self._attr_icon = description.icon

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        if self.entity_description.value_fn is None:
            return None

        # Try to get fresh data from coordinator
        if self.coordinator.data:
            try:
                # For WAN sensors, get data from wan_status
                wan_status = self.coordinator.data.get("wan_status", {})
                connections = wan_status.get("connection", [])
                
                for connection in connections:
                    if str(connection.get("id", "")) == self._wan_id:
                        return self.entity_description.value_fn(connection)
            except Exception:
                # If anything goes wrong, fall back to initial data
                pass
                
        # Fall back to initial sensor data
        return self.entity_description.value_fn(self._initial_sensor_data)


class PeplinkRouterBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A router-level binary sensor read from one item of the coordinator data."""

    entity_description: PeplinkBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeplinkDataUpdateCoordinator,
        description: PeplinkBinarySensorEntityDescription,
        item_fn: Callable[[dict], dict | None],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self.entity_description = description
        self._item_fn = item_fn
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
        )
        if description.icon:
            self._attr_icon = description.icon

    def _item(self) -> dict | None:
        """Return this sensor's item from the latest coordinator data."""
        return self._item_fn(self.coordinator.data or {})

    @property
    def available(self) -> bool:
        """Return True while the router still reports this item."""
        return super().available and self._item() is not None

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        item = self._item()
        if item is None or self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(item)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        item = self._item()
        if item is None or self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(item)
