"""Support for Peplink sensors."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfTemperature,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
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

    value_fn: Callable[[Any], StateType] | None = None


SENSOR_TYPES: tuple[PeplinkSensorEntityDescription, ...] = (
    # System sensors
    PeplinkSensorEntityDescription(
        key="system_temperature",
        translation_key=None,
        name="System Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("temperature"),
    ),
    PeplinkSensorEntityDescription(
        key="system_temperature_threshold",
        translation_key=None,
        name="System Temperature Threshold",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("threshold"),
    ),
    PeplinkSensorEntityDescription(
        key="fan_1_speed",
        translation_key=None,
        name="Fan 1 Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("speed"),
    ),
    PeplinkSensorEntityDescription(
        key="fan_1_percentage",
        translation_key=None,
        name="Fan 1 Percentage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("percentage"),
    ),
    PeplinkSensorEntityDescription(
        key="fan_2_speed",
        translation_key=None,
        name="Fan 2 Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("speed"),
    ),
    PeplinkSensorEntityDescription(
        key="fan_2_percentage",
        translation_key=None,
        name="Fan 2 Percentage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("percentage"),
    ),
    # WAN traffic sensors - these will be created dynamically per WAN
    PeplinkSensorEntityDescription(
        key="wan_rx_bytes",
        translation_key=None,
        name="WAN Received",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda x: x.get("rx_bytes"),
    ),
    PeplinkSensorEntityDescription(
        key="wan_tx_bytes",
        translation_key=None,
        name="WAN Sent",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda x: x.get("tx_bytes"),
    ),
    PeplinkSensorEntityDescription(
        key="wan_rx_rate",
        translation_key=None,
        name="WAN Receive Rate",
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("rx_rate"),
    ),
    PeplinkSensorEntityDescription(
        key="wan_tx_rate",
        translation_key=None,
        name="WAN Send Rate",
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get("tx_rate"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Peplink sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities: list[PeplinkSensor] = []

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

    # Add fan sensors
    if coordinator.data.get("fan_speeds", {}).get("fans"):
        fans = coordinator.data["fan_speeds"]["fans"]
        for fan_num, fan in enumerate(fans, 1):
            for description in SENSOR_TYPES:
                if description.key in [f"fan_{fan_num}_speed", f"fan_{fan_num}_percentage"]:
                    entities.append(
                        PeplinkSensor(
                            coordinator=coordinator,
                            description=description,
                            sensor_data=fan,
                        )
                    )

    # Add WAN traffic sensors
    if coordinator.data.get("traffic_stats", {}).get("stats"):
        for wan in coordinator.data["traffic_stats"]["stats"]:
            for description in SENSOR_TYPES:
                if description.key.startswith("wan_"):
                    # Create a copy of the description for this specific WAN
                    wan_description = PeplinkSensorEntityDescription(
                        key=f"{description.key}_{wan['wan_id']}",
                        translation_key=None,
                        name=f"{wan['name']} {description.name}",
                        native_unit_of_measurement=description.native_unit_of_measurement,
                        device_class=description.device_class,
                        state_class=description.state_class,
                        value_fn=description.value_fn,
                    )
                    entities.append(
                        PeplinkSensor(
                            coordinator=coordinator,
                            description=wan_description,
                            sensor_data=wan,
                        )
                    )

    async_add_entities(entities)


class PeplinkSensor(CoordinatorEntity[PeplinkDataUpdateCoordinator], SensorEntity):
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
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Peplink",
            model=coordinator.model,
            name=coordinator.host,
            sw_version=coordinator.firmware,
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # Find the current sensor data based on the key
        if self.entity_description.key.startswith("system_temperature"):
            thermal_sensors = self.coordinator.data.get("thermal_sensors", {})
            if thermal_sensors and thermal_sensors.get("sensors"):
                sensor_data = thermal_sensors["sensors"][0]  # Only one sensor
            else:
                return None
        elif self.entity_description.key.startswith("fan_"):
            fan_num = int(self.entity_description.key.split("_")[1])
            fans = self.coordinator.data.get("fan_speeds", {}).get("fans", [])
            if fan_num <= len(fans):
                sensor_data = fans[fan_num - 1]
            else:
                return None
        elif self.entity_description.key.startswith("wan_"):
            wan_id = self.entity_description.key.split("_")[-1]
            stats = self.coordinator.data.get("traffic_stats", {}).get("stats", [])
            sensor_data = next(
                (stat for stat in stats if stat["wan_id"] == wan_id),
                None,
            )
            if not sensor_data:
                return None
        else:
            return None

        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(sensor_data)

        return None
