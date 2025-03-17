"""Support for Peplink sensors."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable
import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfTemperature,
    UnitOfDataRate,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util
from homeassistant.config_entries import ConfigEntry

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class PeplinkSensorEntityDescription(SensorEntityDescription):
    """Class describing Peplink sensor entities."""

    value_fn: Callable[[dict], Any] | None = None
    icon: str | None = None


@dataclass
class PeplinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Peplink binary sensor entities."""

    value_fn: Callable[[dict], Any] | None = None
    icon: str | None = None


SENSOR_TYPES: tuple[PeplinkSensorEntityDescription, ...] = (
    # System sensors
    PeplinkSensorEntityDescription(
        key="system_temperature",
        translation_key=None,
        name="System Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: x.get("temperature"),
        icon="mdi:thermometer",
    ),
    PeplinkSensorEntityDescription(
        key="system_temperature_threshold",
        translation_key=None,
        name="System Temperature Threshold",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: x.get("threshold"),
        icon="mdi:thermometer-alert",
    ),
    # System-level bandwidth sensors
    PeplinkSensorEntityDescription(
        key="system_download_rate",
        translation_key=None,
        name="System Download",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: round(x.get("rx_rate") / 1_000_000, 2) if x.get("rx_rate") is not None else None,
        icon="mdi:download-network",
    ),
    PeplinkSensorEntityDescription(
        key="system_upload_rate",
        translation_key=None,
        name="System Upload",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: round(x.get("tx_rate") / 1_000_000, 2) if x.get("tx_rate") is not None else None,
        icon="mdi:upload-network",
    ),
    # Device info sensors
    PeplinkSensorEntityDescription(
        key="device_serial_number",
        translation_key=None,
        name="Serial Number",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: x.get("serial_number"),
        icon="mdi:barcode",
    ),
    PeplinkSensorEntityDescription(
        key="device_name",
        translation_key=None,
        name="Device Name",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: x.get("name"),
        icon="mdi:label",
    ),
    PeplinkSensorEntityDescription(
        key="device_firmware_version",
        translation_key=None,
        name="Firmware Version",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: x.get("firmware_version"),
        icon="mdi:package-variant-closed",
    ),
    # WAN traffic sensors - these will be created dynamically per WAN
    PeplinkSensorEntityDescription(
        key="wan_download_rate",
        translation_key=None,
        name="Download",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: round(x.get("rx_rate") / 1_000_000, 2) if x.get("rx_rate") is not None else None,
        icon="mdi:download-network",
    ),
    PeplinkSensorEntityDescription(
        key="wan_upload_rate",
        translation_key=None,
        name="Upload",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: round(x.get("tx_rate") / 1_000_000, 2) if x.get("tx_rate") is not None else None,
        icon="mdi:upload-network",
    ),
    PeplinkSensorEntityDescription(
        key="wan_type",
        translation_key=None,
        name="Type",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        value_fn=lambda x: _translate_wan_type(x.get("type")),
        icon="mdi:lan",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PeplinkSensorEntityDescription(
        key="wan_name",
        translation_key=None,
        name="Name",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        value_fn=lambda x: x.get("name"),
        icon="mdi:tag",
    ),
    PeplinkSensorEntityDescription(
        key="wan_ip",
        translation_key=None,
        name="IP Address",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        value_fn=lambda x: x.get("ip"),
        icon="mdi:ip-network",
    ),
    PeplinkSensorEntityDescription(
        key="wan_up_since",
        translation_key=None,
        name="Up Since",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        state_class=None,
        # Calculate the "up since" timestamp by subtracting uptime from current time
        value_fn=lambda x: (
            dt_util.utcnow() - datetime.timedelta(seconds=x.get("uptime"))
            if x.get("uptime") is not None
            else None
        ),
        icon="mdi:clock-start",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # WiFi specific sensors for WiFi WAN connections
    PeplinkSensorEntityDescription(
        key="wifi_signal_strength",
        translation_key=None,
        name="WiFi Signal Strength",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("wifi", {}).get("signal", {}).get("strength"),
        icon="mdi:wifi-strength-4",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PeplinkSensorEntityDescription(
        key="wifi_ssid",
        translation_key=None,
        name="WiFi SSID",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        value_fn=lambda x: x.get("wifi", {}).get("ssid"),
        icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PeplinkSensorEntityDescription(
        key="wifi_bssid",
        translation_key=None,
        name="WiFi BSSID",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=None,
        value_fn=lambda x: x.get("wifi", {}).get("bssid"),
        icon="mdi:wifi-marker",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PeplinkSensorEntityDescription(
        key="wifi_channel",
        translation_key=None,
        name="WiFi Channel",
        native_unit_of_measurement=None,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("wifi", {}).get("channel"),
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Peplink sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    # Add system sensors
    thermal_sensors = coordinator.data.get("thermal_sensors", {})
    if thermal_sensors and thermal_sensors.get("sensors"):
        sensor = thermal_sensors["sensors"][0]  # Only one sensor
        for description in SENSOR_TYPES:
            if description.key in ["system_temperature", "system_temperature_threshold"]:
                entities.append(
                    PeplinkSensor(
                        coordinator=coordinator,
                        description=description,
                        sensor_data=sensor,
                    )
                )

    # Add system-level bandwidth sensors
    if coordinator.data.get("traffic_stats", {}).get("stats"):
        raw_traffic_data = coordinator.data["traffic_stats"]["stats"]
        # Create system download/upload sensors
        for description in SENSOR_TYPES:
            if description.key in ["system_download_rate", "system_upload_rate"]:
                # Prepare system-level traffic data
                system_traffic_data = {
                    "rx_rate": 0,
                    "tx_rate": 0,
                }
                # Sum up all WAN interfaces data
                for wan in raw_traffic_data:
                    system_traffic_data["rx_rate"] += wan.get("rx_rate", 0)
                    system_traffic_data["tx_rate"] += wan.get("tx_rate", 0)
                
                entities.append(
                    PeplinkSensor(
                        coordinator=coordinator,
                        description=description,
                        sensor_data=system_traffic_data,
                    )
                )

    # Add device info sensors
    device_info = coordinator.data.get("device_info", {}).get("device_info", {})
    if device_info:
        for description in SENSOR_TYPES:
            if description.key.startswith("device_"):
                entities.append(
                    PeplinkSensor(
                        coordinator=coordinator,
                        description=description,
                        sensor_data=device_info,
                    )
                )

    # Add fan sensors
    if coordinator.data.get("fan_speeds", {}).get("fans"):
        fans = coordinator.data["fan_speeds"]["fans"]
        for fan_num, fan in enumerate(fans, 1):
            # Dynamically create a fan speed sensor for each fan
            fan_speed_description = PeplinkSensorEntityDescription(
                key=f"fan_{fan_num}_speed",
                translation_key=None,
                name=f"Fan {fan_num} Speed",
                native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
                device_class=None,
                state_class=SensorStateClass.MEASUREMENT,
                entity_category=EntityCategory.DIAGNOSTIC,
                icon="mdi:fan",
                value_fn=lambda x: x.get("speed"),
            )
            entities.append(
                PeplinkSensor(
                    coordinator=coordinator,
                    description=fan_speed_description,
                    sensor_data=fan,
                )
            )

    # Add WAN traffic sensors
    if coordinator.data.get("traffic_stats", {}).get("stats"):
        wan_stats = coordinator.data["traffic_stats"]["stats"]
        
        # Get the WAN status data - Fix key mismatch here
        wan_status = coordinator.data.get("wan_status", {})
        wan_connections = wan_status.get("connection", [])
        
        for wan in wan_stats:
            wan_id = wan['wan_id']
            wan_name = wan['name']
            
            # Create device info for this WAN
            device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_wan{wan_id}")},
                manufacturer="Peplink",
                model="WAN Connection",
                name=f"Peplink {coordinator.host} WAN{wan_id}",
                via_device=(DOMAIN, coordinator.config_entry.entry_id),
            )
            
            # Find matching WAN connection data
            wan_connection = None
            for connection in wan_connections:
                if str(connection.get("id", "")) == str(wan_id):
                    wan_connection = connection
                    break
            
            # Create traffic rate sensors
            for description in SENSOR_TYPES:
                if description.key in ["wan_download_rate", "wan_upload_rate"]:
                    # Create a copy of the description for this specific WAN
                    sensor_description = PeplinkSensorEntityDescription(
                        key=f"{description.key.replace('wan_', '')}",
                        translation_key=description.translation_key,
                        name=description.name,
                        native_unit_of_measurement=description.native_unit_of_measurement,
                        device_class=description.device_class,
                        state_class=description.state_class,
                        icon=description.icon,  # Use the icon from the original description
                        value_fn=description.value_fn,
                    )
                    entities.append(
                        PeplinkWANSensor(
                            coordinator=coordinator,
                            description=sensor_description,
                            sensor_data=wan,
                            device_info=device_info,
                            wan_id=wan_id,
                        )
                    )
            
            # Add all relevant sensors if WAN connection data is available
            if wan_connection:
                # Add a connection status sensor
                message_description = PeplinkSensorEntityDescription(
                    key="message",
                    translation_key=None,
                    name="Message",
                    native_unit_of_measurement=None,
                    device_class=None,
                    state_class=None,
                    value_fn=lambda x: x.get("message"),
                    icon="mdi:network",
                )
                entities.append(
                    PeplinkWANSensor(
                        coordinator=coordinator,
                        description=message_description,
                        sensor_data=wan_connection,
                        device_info=device_info,
                        wan_id=wan_id,
                    )
                )
                
                # Add all relevant sensors
                for description in SENSOR_TYPES:
                    if description.key.startswith("wan_") and description.key not in ["wan_download_rate", "wan_upload_rate", "wan_message", "wan_uptime"]:
                        # Create a copy of the description for this specific WAN
                        sensor_description = PeplinkSensorEntityDescription(
                            key=f"{description.key.replace('wan_', '')}",
                            translation_key=description.translation_key,
                            name=description.name,
                            native_unit_of_measurement=description.native_unit_of_measurement,
                            device_class=description.device_class,
                            state_class=description.state_class,
                            icon=description.icon,  # Use the icon from the original description
                            value_fn=description.value_fn,
                        )
                        entities.append(
                            PeplinkWANSensor(
                                coordinator=coordinator,
                                description=sensor_description,
                                sensor_data=wan_connection,
                                device_info=device_info,
                                wan_id=wan_id,
                            )
                        )

                # Add WiFi specific sensors if this is a WiFi WAN connection
                if wan_connection.get("type") == "wifi":
                    for description in SENSOR_TYPES:
                        if description.key.startswith("wifi_"):
                            # Create a copy of the description for this specific WiFi WAN
                            sensor_description = PeplinkSensorEntityDescription(
                                key=description.key,
                                translation_key=description.translation_key,
                                name=description.name,
                                native_unit_of_measurement=description.native_unit_of_measurement,
                                device_class=description.device_class,
                                state_class=description.state_class,
                                icon=description.icon,
                                value_fn=description.value_fn,
                            )
                            entities.append(
                                PeplinkWANSensor(
                                    coordinator=coordinator,
                                    description=sensor_description,
                                    sensor_data=wan_connection,
                                    device_info=device_info,
                                    wan_id=wan_id,
                                )
                            )

    async_add_entities(entities)


class PeplinkSensor(CoordinatorEntity, SensorEntity):
    """Implementation of a Peplink sensor."""

    entity_description: PeplinkSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeplinkDataUpdateCoordinator,
        description: PeplinkSensorEntityDescription,
        sensor_data: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self.entity_description = description
        self._sensor_data_key = None
        self._sensor_data_id = None
        
        # Store identifiers to find data in coordinator updates
        if description.key.startswith("system_temperature"):
            self._sensor_data_key = "thermal_sensors"
            self._sensor_data_id = "System"  # System temperature sensor name
        elif description.key.startswith("fan_"):
            self._sensor_data_key = "fan_speeds"
            # Extract fan number from key (e.g., fan_1_speed -> 1)
            try:
                self._sensor_data_id = description.key.split("_")[1]
            except (IndexError, ValueError):
                self._sensor_data_id = None
        elif description.key.startswith("device_"):
            self._sensor_data_key = "device_info"
            
        # Keep a reference to the initial data as fallback
        self._initial_sensor_data = sensor_data
        
        # Use IP address as the prefix for consistent entity IDs
        self._attr_unique_id = f"{coordinator.host}_{description.key}"
        
        # Use the device name from API if available, otherwise fallback to IP
        device_name = coordinator.device_name or f"Peplink {coordinator.host}"
        
        # Create model string with available info
        model_string = coordinator.model or "Router"
        if coordinator.product_code and coordinator.hardware_revision:
            model_string = f"{model_string} ({coordinator.product_code} HW {coordinator.hardware_revision})"
        elif coordinator.product_code:
            model_string = f"{model_string} ({coordinator.product_code})"
        elif coordinator.hardware_revision:
            model_string = f"{model_string} (HW {coordinator.hardware_revision})"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Peplink",
            model=model_string,
            name=device_name,
            sw_version=coordinator.firmware,
        )
        # Set custom icon if provided
        if description.icon:
            self._attr_icon = description.icon

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.value_fn is None:
            return None

        # Try to get fresh data from coordinator
        if self.coordinator.data and self._sensor_data_key:
            try:
                if self._sensor_data_key == "thermal_sensors":
                    sensors = self.coordinator.data.get("thermal_sensors", {}).get("sensors", [])
                    for sensor in sensors:
                        if sensor.get("name") == self._sensor_data_id:
                            return self.entity_description.value_fn(sensor)
                
                elif self._sensor_data_key == "fan_speeds":
                    fans = self.coordinator.data.get("fan_speeds", {}).get("fans", [])
                    for fan in fans:
                        if str(fan.get("id", "")) == self._sensor_data_id:
                            return self.entity_description.value_fn(fan)
                
                elif self._sensor_data_key == "device_info":
                    device_info = self.coordinator.data.get("device_info", {}).get("device_info", {})
                    if device_info:
                        return self.entity_description.value_fn(device_info)
            except Exception:
                # If anything goes wrong with data access, fall back to initial data
                pass
                
        # Fall back to initial sensor data
        return self.entity_description.value_fn(self._initial_sensor_data)


class PeplinkWANSensor(CoordinatorEntity, SensorEntity):
    """Implementation of a Peplink WAN sensor."""

    entity_description: PeplinkSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeplinkDataUpdateCoordinator,
        description: PeplinkSensorEntityDescription,
        sensor_data: dict[str, Any],
        device_info: DeviceInfo,
        wan_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self.entity_description = description
        self._wan_id = wan_id
        # Keep reference to initial data
        self._initial_sensor_data = sensor_data
        
        # Use IP address as the prefix for consistent entity IDs
        self._attr_unique_id = f"{coordinator.host}_wan{wan_id}_{description.key}_{description.name.lower().replace(' ', '_')}"
        
        # Use the device name from API if available, otherwise fallback to IP
        device_name = coordinator.device_name or f"Peplink {coordinator.host}"
        
        self._attr_device_info = device_info
        
        # Add extra attributes for IP sensor
        self._extra_attrs = {}
        if description.key == "ip" and sensor_data:
            self._extra_attrs = {
                "gateway": sensor_data.get("gateway"),
                "dns": sensor_data.get("dns", []),
                "mask": sensor_data.get("mask"),
            }
            
        # Set custom icon if provided
        if description.icon:
            self._attr_icon = description.icon

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.value_fn is None:
            return None

        # Check if we're dealing with traffic rate sensors
        is_traffic_sensor = self.entity_description.key in ["download_rate", "upload_rate"]
        
        # Try to get fresh data from coordinator
        if self.coordinator.data:
            try:
                if is_traffic_sensor:
                    # For traffic sensors, get data from traffic_stats
                    stats = self.coordinator.data.get("traffic_stats", {}).get("stats", [])
                    for stat in stats:
                        if str(stat.get("wan_id", "")) == self._wan_id:
                            return self.entity_description.value_fn(stat)
                else:
                    # For other WAN sensors, get data from wan_status
                    wan_status = self.coordinator.data.get("wan_status", {})
                    connections = wan_status.get("connection", [])  # Use the correct key based on setup_entry
                    
                    for connection in connections:
                        if str(connection.get("id", "")) == self._wan_id:
                            # Update extra attributes if needed
                            if self.entity_description.key == "ip":
                                self._extra_attrs = {
                                    "gateway": connection.get("gateway"),
                                    "dns": connection.get("dns", []),
                                    "mask": connection.get("mask"),
                                }
                            return self.entity_description.value_fn(connection)
            except Exception:
                # If anything goes wrong, fall back to initial data
                pass
                
        # Fall back to initial sensor data
        return self.entity_description.value_fn(self._initial_sensor_data)
        
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return self._extra_attrs


def _translate_wan_type(wan_type: str) -> str:
    """Translate WAN type to more user-friendly format."""
    if not wan_type:
        return None
        
    type_map = {
        "modem": "Modem",
        "wireless": "Wireless",
        "gobi": "Cellular",
        "cellular": "Cellular",
        "ipsec": "IPSec VPN",
        "adsl": "ADSL",
        "wifi": "WiFi",
        "ethernet": "Ethernet"
    }
    
    return type_map.get(wan_type.lower(), wan_type)
