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
        self._sensor_data = sensor_data
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

        return self.entity_description.value_fn(self._sensor_data)


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
        self._sensor_data = sensor_data
        # Use IP address as the prefix for consistent entity IDs
        self._attr_unique_id = f"{coordinator.host}_wan{wan_id}_{description.key}_{description.name.lower().replace(' ', '_')}"
        
        # Use the device name from API if available, otherwise fallback to IP
        device_name = coordinator.device_name or f"Peplink {coordinator.host}"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_wan{wan_id}")},
            manufacturer="Peplink",
            model="WAN Connection",
            name=f"{device_name} WAN{wan_id}",
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )
        
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

        return self.entity_description.value_fn(self._sensor_data)
        
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
        "ethernet": "Ethernet"
    }
    
    return type_map.get(wan_type.lower(), wan_type)
