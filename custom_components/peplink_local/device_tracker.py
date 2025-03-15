"""Device tracker platform for Peplink Local integration."""
import logging
from typing import Any, Dict, List, Optional, Set

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    ATTR_CLIENT_NAME,
    ATTR_CLIENT_MAC,
    ATTR_CLIENT_IP,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up Peplink device tracker based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    _LOGGER.debug("Setting up Peplink device trackers for entry: %s", entry.entry_id)
    
    # Wait for coordinator to get data
    await coordinator.async_config_entry_first_refresh()
    
    entities = []
    
    # Create a device tracker for each client
    if coordinator.data and "clients" in coordinator.data:
        _LOGGER.debug("Client data found in coordinator: %s", coordinator.data["clients"])
        client_data = coordinator.data["clients"]
        
        if "client" in client_data:
            _LOGGER.debug("Clients found: %s", client_data["client"])
            for client in client_data["client"]:
                if "mac" in client:
                    _LOGGER.debug("Creating device tracker for client: %s (%s)", 
                                 client.get("name", "Unknown"), client.get("mac"))
                    entities.append(
                        PeplinkClientTracker(
                            coordinator,
                            entry.entry_id,
                            client.get("name", "Unknown"),
                            client.get("mac"),
                        )
                    )
                else:
                    _LOGGER.warning("Client missing MAC address: %s", client)
        else:
            _LOGGER.warning("No 'client' key in client data: %s", client_data)
    else:
        _LOGGER.warning("No client data found in coordinator data: %s", coordinator.data)
    
    if entities:
        _LOGGER.debug("Adding %d Peplink client device trackers", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No Peplink client device trackers created")


class PeplinkClientTracker(CoordinatorEntity, ScannerEntity):
    """Representation of a Peplink client device tracker."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        client_name: str,
        client_mac: str,
    ):
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._config_entry_id = config_entry_id
        self._client_name = client_name
        self._client_mac = client_mac
        # Use IP address as the prefix for consistent entity IDs
        self._attr_unique_id = f"{coordinator.host}_client_{client_mac}"
        self._attr_name = f"{client_name}"
        self._is_connected = False
        self._ip_address = None
        self._mac_address = client_mac
        self._attributes = {}
        self._attr_has_entity_name = True
        
        # Update initial state
        self._update_device_data()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Peplink router."""
        # Get the host from the coordinator if possible
        host = self.coordinator.host if hasattr(self.coordinator, "host") else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            manufacturer="Peplink",
            model="Router",
            name=f"Peplink {host} System" if host else "Peplink System",
        )

    @property
    def source_type(self) -> str:
        """Return the source type of the device."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        return self._is_connected

    @property
    def ip_address(self) -> Optional[str]:
        """Return the IP address of the device."""
        return self._ip_address

    @property
    def mac_address(self) -> Optional[str]:
        """Return the MAC address of the device."""
        return self._mac_address

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the device state attributes."""
        return self._attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_device_data()
        self.async_write_ha_state()

    def _update_device_data(self) -> None:
        """Update device data from the coordinator."""
        self._is_connected = False
        self._ip_address = None
        self._attributes = {
            ATTR_CLIENT_NAME: self._client_name,
            ATTR_CLIENT_MAC: self._client_mac,
        }
        
        if (
            self.coordinator.data
            and "clients" in self.coordinator.data
            and "client" in self.coordinator.data["clients"]
        ):
            for client in self.coordinator.data["clients"]["client"]:
                if client.get("mac") == self._client_mac:
                    self._is_connected = client.get("connected", False)
                    self._ip_address = client.get("ip")
                    
                    # Add all client attributes
                    for key, value in client.items():
                        if key not in ["mac", "name", "ip", "connected"]:
                            self._attributes[key] = value
