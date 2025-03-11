"""Sensor platform for Peplink Local integration."""
import logging
from typing import Any, Dict, List, Optional
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    ATTR_WAN_ID,
    ATTR_WAN_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up Peplink sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    _LOGGER.debug("Setting up Peplink sensors for entry: %s", entry.entry_id)
    
    # Wait for coordinator to get data
    await coordinator.async_config_entry_first_refresh()
    
    entities = []
    
    # Check if we have WAN data
    if coordinator.data and "wan" in coordinator.data:
        _LOGGER.debug("WAN data found in coordinator: %s", coordinator.data["wan"])
        wan_data = coordinator.data["wan"]
        
        # Create sensors for each WAN connection
        if "connection" in wan_data:
            _LOGGER.debug("WAN connections found: %s", wan_data["connection"])
            for wan in wan_data["connection"]:
                # Only create sensors for enabled WAN interfaces
                if "id" in wan and "name" in wan and wan.get("enable", False):
                    _LOGGER.debug("Creating sensors for WAN: %s (%s)", wan["name"], wan["id"])
                    
                    # Create a device for this WAN interface
                    device_id = f"{entry.entry_id}_wan_{wan['id']}"
                    device_name = f"Peplink WAN {wan['name']}"
                    
                    # Create binary sensor for connection status
                    entities.append(
                        PeplinkWanConnectedSensor(
                            coordinator,
                            entry.entry_id,
                            wan["id"],
                            wan["name"],
                            device_id,
                            device_name,
                        )
                    )
                    
                    # Create sensor for message
                    entities.append(
                        PeplinkWanMessageSensor(
                            coordinator,
                            entry.entry_id,
                            wan["id"],
                            wan["name"],
                            device_id,
                            device_name,
                        )
                    )
                    
                    # Create sensor for IP
                    entities.append(
                        PeplinkWanIPSensor(
                            coordinator,
                            entry.entry_id,
                            wan["id"],
                            wan["name"],
                            device_id,
                            device_name,
                        )
                    )
                    
                    # Create sensor for Gateway
                    entities.append(
                        PeplinkWanGatewaySensor(
                            coordinator,
                            entry.entry_id,
                            wan["id"],
                            wan["name"],
                            device_id,
                            device_name,
                        )
                    )
                    
                    # Create sensor for Uptime
                    entities.append(
                        PeplinkWanUptimeSensor(
                            coordinator,
                            entry.entry_id,
                            wan["id"],
                            wan["name"],
                            device_id,
                            device_name,
                        )
                    )
                else:
                    if not wan.get("enable", False):
                        _LOGGER.info("Skipping disabled WAN: %s", wan.get("name", wan.get("id", "Unknown")))
                    else:
                        _LOGGER.warning("WAN missing required fields: %s", wan)
        else:
            _LOGGER.warning("No 'connection' key in WAN data: %s", wan_data)
    else:
        _LOGGER.warning("No WAN data found in coordinator data: %s", coordinator.data)
    
    if entities:
        _LOGGER.debug("Adding %d Peplink WAN entities", len(entities))
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No Peplink WAN entities created")


class PeplinkWanBaseSensor(CoordinatorEntity):
    """Base class for Peplink WAN sensors."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        wan_name: str,
        device_id: str,
        device_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry_id = config_entry_id
        self._wan_id = wan_id
        self._wan_name = wan_name
        self._device_id = device_id
        self._device_name = device_name
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Peplink WAN interface."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Peplink",
            model="WAN Interface",
            via_device=(DOMAIN, self._config_entry_id),
        )

    def get_wan_data(self) -> Dict[str, Any]:
        """Get the WAN data for this interface."""
        if (
            self.coordinator.data
            and "wan" in self.coordinator.data
            and "connection" in self.coordinator.data["wan"]
        ):
            for wan in self.coordinator.data["wan"]["connection"]:
                if wan.get("id") == self._wan_id:
                    return wan
        return {}


class PeplinkWanConnectedSensor(PeplinkWanBaseSensor, BinarySensorEntity):
    """Representation of a Peplink WAN connection status sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        wan_name: str,
        device_id: str,
        device_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, wan_name, device_id, device_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_connected"
        self._attr_name = f"{wan_name} Connected"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool:
        """Return true if the WAN interface is connected."""
        wan_data = self.get_wan_data()
        return wan_data.get("message") == "Connected"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_WAN_ID: self._wan_id,
            ATTR_WAN_NAME: self._wan_name,
        }


class PeplinkWanMessageSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN message sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        wan_name: str,
        device_id: str,
        device_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, wan_name, device_id, device_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_message"
        self._attr_name = f"{wan_name} Message"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        return wan_data.get("message", "Unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_WAN_ID: self._wan_id,
            ATTR_WAN_NAME: self._wan_name,
        }


class PeplinkWanIPSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN IP sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        wan_name: str,
        device_id: str,
        device_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, wan_name, device_id, device_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_ip"
        self._attr_name = f"{wan_name} IP"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        return wan_data.get("ip", "Unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        attrs = {
            ATTR_WAN_ID: self._wan_id,
            ATTR_WAN_NAME: self._wan_name,
        }
        
        wan_data = self.get_wan_data()
        if "mask" in wan_data:
            attrs["subnet_mask"] = wan_data["mask"]
        if "dns" in wan_data and isinstance(wan_data["dns"], list):
            attrs["dns_servers"] = ", ".join(wan_data["dns"])
            
        return attrs


class PeplinkWanGatewaySensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN Gateway sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        wan_name: str,
        device_id: str,
        device_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, wan_name, device_id, device_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_gateway"
        self._attr_name = f"{wan_name} Gateway"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        return wan_data.get("gateway", "Unknown")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_WAN_ID: self._wan_id,
            ATTR_WAN_NAME: self._wan_name,
        }


class PeplinkWanUptimeSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN Uptime sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        wan_name: str,
        device_id: str,
        device_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, wan_name, device_id, device_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_uptime"
        self._attr_name = f"{wan_name} Uptime"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_native_unit_of_measurement = "s"
        self._attr_suggested_display_precision = 0

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        return wan_data.get("uptime", 0)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        wan_data = self.get_wan_data()
        uptime = wan_data.get("uptime", 0)
        
        attrs = {
            ATTR_WAN_ID: self._wan_id,
            ATTR_WAN_NAME: self._wan_name,
        }
        
        if uptime:
            # Add formatted uptime
            td = timedelta(seconds=uptime)
            days = td.days
            hours, remainder = divmod(td.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            attrs["uptime_formatted"] = f"{days}d {hours}h {minutes}m {seconds}s"
            
        return attrs
