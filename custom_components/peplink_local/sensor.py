"""Sensor platform for Peplink Local integration."""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ATTR_WAN_ID,
)

_LOGGER = logging.getLogger(__name__)

# Connection type mapping to human-readable names
CONNECTION_TYPE_MAP = {
    "modem": "Modem",
    "wireless": "Wireless",
    "gobi": "Cellular",
    "cellular": "Cellular",
    "ipsec": "IPsec",
    "adsl": "ADSL",
    "ethernet": "Ethernet",
}


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
                if "id" in wan and wan.get("enable", False):
                    wan_id = wan["id"]
                    wan_name = wan.get("name", f"WAN{wan_id}")
                    standard_name = f"WAN{wan_id}"
                    
                    _LOGGER.debug("Creating sensors for %s (ID: %s)", standard_name, wan_id)
                    
                    # Create name sensor
                    entities.append(
                        PeplinkWanNameSensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
                            wan_name,
                        )
                    )
                    
                    # Create binary sensor for connection status
                    entities.append(
                        PeplinkWanConnectedSensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
                        )
                    )
                    
                    # Create sensor for message
                    entities.append(
                        PeplinkWanMessageSensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
                        )
                    )
                    
                    # Create sensor for IP
                    entities.append(
                        PeplinkWanIPSensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
                        )
                    )
                    
                    # Create sensor for connection type
                    entities.append(
                        PeplinkWanTypeSensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
                        )
                    )
                    
                    # Create sensor for priority
                    entities.append(
                        PeplinkWanPrioritySensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
                        )
                    )
                    
                    # Create sensor for up since timestamp
                    entities.append(
                        PeplinkWanUpSinceSensor(
                            coordinator,
                            entry.entry_id,
                            wan_id,
                            standard_name,
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
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry_id = config_entry_id
        self._wan_id = wan_id
        self._standard_name = standard_name
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Peplink WAN interface."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._config_entry_id}_wan_{self._wan_id}")},
            name=f"Peplink {self._standard_name}",
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


class PeplinkWanNameSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN name sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
        configured_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._configured_name = configured_name
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_name"
        self._attr_name = f"{standard_name} Name"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        return wan_data.get("name", self._configured_name)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_WAN_ID: self._wan_id,
        }


class PeplinkWanConnectedSensor(PeplinkWanBaseSensor, BinarySensorEntity):
    """Representation of a Peplink WAN connection status sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_connected"
        self._attr_name = f"{standard_name} Connected"
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
        }


class PeplinkWanMessageSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN message sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_message"
        self._attr_name = f"{standard_name} Message"

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
        }


class PeplinkWanIPSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN IP sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_ip"
        self._attr_name = f"{standard_name} IP"

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
        }
        
        wan_data = self.get_wan_data()
        if "gateway" in wan_data:
            attrs["gateway"] = wan_data["gateway"]
        if "mask" in wan_data:
            attrs["subnet_mask"] = wan_data["mask"]
        if "dns" in wan_data and isinstance(wan_data["dns"], list):
            attrs["dns_servers"] = ", ".join(wan_data["dns"])
            
        return attrs


class PeplinkWanTypeSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN connection type sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_type"
        self._attr_name = f"{standard_name} Connection Type"

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        raw_type = wan_data.get("type", "Unknown")
        return CONNECTION_TYPE_MAP.get(raw_type, raw_type)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        wan_data = self.get_wan_data()
        return {
            ATTR_WAN_ID: self._wan_id,
            "raw_type": wan_data.get("type", "Unknown"),
        }


class PeplinkWanPrioritySensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN priority sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_priority"
        self._attr_name = f"{standard_name} Priority"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        return wan_data.get("priority", 0)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        return {
            ATTR_WAN_ID: self._wan_id,
        }


class PeplinkWanUpSinceSensor(PeplinkWanBaseSensor, SensorEntity):
    """Representation of a Peplink WAN Up Since sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        config_entry_id: str,
        wan_id: str,
        standard_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry_id, wan_id, standard_name)
        self._attr_unique_id = f"{config_entry_id}_wan_{wan_id}_last_connected"
        self._attr_name = f"{standard_name} Up Since"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._last_timestamp = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        wan_data = self.get_wan_data()
        uptime = wan_data.get("uptime", 0)
        
        if uptime is not None and uptime > 0:
            # Calculate the timestamp when the interface was last connected
            self._last_timestamp = dt_util.utcnow() - timedelta(seconds=uptime)
        
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime:
        """Return the state of the sensor."""
        wan_data = self.get_wan_data()
        uptime = wan_data.get("uptime", 0)
        
        if uptime is not None and uptime > 0:
            # Calculate the timestamp when the interface was last connected
            return dt_util.utcnow() - timedelta(seconds=uptime)
        
        return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        wan_data = self.get_wan_data()
        uptime = wan_data.get("uptime", 0)
        
        attrs = {
            ATTR_WAN_ID: self._wan_id,
        }
        
        if uptime:
            # Add uptime in seconds
            attrs["uptime_seconds"] = uptime
            
            # Add formatted uptime
            td = timedelta(seconds=uptime)
            days = td.days
            hours, remainder = divmod(td.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            attrs["uptime_formatted"] = f"{days}d {hours}h {minutes}m {seconds}s"
            
        return attrs
