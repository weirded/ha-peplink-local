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
    UnitOfLength,
    UnitOfSpeed,
    UnitOfPower,
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
from homeassistant.util.variance import ignore_variance
from homeassistant.config_entries import ConfigEntry

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN
from .ap_one import ap_one_sensor_entities

_LOGGER = logging.getLogger(__name__)


@dataclass
class PeplinkSensorEntityDescription(SensorEntityDescription):
    """Class describing Peplink sensor entities."""

    value_fn: Callable[[dict], Any] | None = None
    icon: str | None = None
    attributes_fn: Callable[[dict], dict[str, Any]] | None = None


@dataclass
class PeplinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Peplink binary sensor entities."""

    value_fn: Callable[[dict], Any] | None = None
    icon: str | None = None


uptime_to_stable_datetime = ignore_variance(
    lambda value: dt_util.utcnow() - datetime.timedelta(seconds=value),
    datetime.timedelta(minutes=1),
)

device_uptime_to_stable_datetime = ignore_variance(
    lambda value: dt_util.utcnow() - datetime.timedelta(seconds=value),
    datetime.timedelta(minutes=1),
)

starlink_uptime_to_stable_datetime = ignore_variance(
    lambda value: dt_util.utcnow() - datetime.timedelta(seconds=value),
    datetime.timedelta(minutes=1),
)


def _starlink(connection: dict) -> dict:
    """Return the Starlink dish data the router reports for a Starlink WAN."""
    return connection.get("starlink") or {}


def _starlink_rate(connection: dict, direction: str) -> float | None:
    """Return the dish's current download or upload rate in Mbit/s."""
    bandwidth = _starlink(connection).get("bandwidth") or {}
    value = bandwidth.get(direction)
    if value is None:
        return None
    scale = {"bps": 1, "kbps": 1_000, "Mbps": 1_000_000}.get(bandwidth.get("unit", "bps"), 1)
    return round(value * scale / 1_000_000, 2)


def _percent(value: float | None, digits: int) -> float | None:
    """Convert a 0-1 fraction to a percentage."""
    return round(value * 100, digits) if value is not None else None


def _cellular(connection: dict) -> dict:
    """Return the cellular data the router reports for a cellular WAN."""
    return connection.get("cellular") or {}


def _primary_band(connection: dict) -> dict:
    """Return the first band of the first radio access technology (the serving cell)."""
    rats = _cellular(connection).get("rat") or []
    bands = (rats[0].get("band") or []) if rats else []
    return bands[0] if bands else {}


# Per-WAN sensors for a WAN the router reports as Starlink (it polls the dish itself)
STARLINK_SENSOR_TYPES: tuple[PeplinkSensorEntityDescription, ...] = (
    PeplinkSensorEntityDescription(
        key="starlink_ping",
        name="Starlink Ping",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: (
            round(_starlink(x)["latency"]["popPing"], 1)
            if _starlink(x).get("latency", {}).get("popPing") is not None
            else None
        ),
        icon="mdi:speedometer",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_download",
        name="Starlink Download",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _starlink_rate(x, "download"),
        icon="mdi:download-network",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_upload",
        name="Starlink Upload",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _starlink_rate(x, "upload"),
        icon="mdi:upload-network",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_obstruction",
        name="Starlink Obstruction",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _percent(_starlink(x).get("obstructionStat", {}).get("fractionObstructed"), 1),
        icon="mdi:satellite-variant",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_time_obstructed",
        name="Starlink Time Obstructed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _percent(_starlink(x).get("obstructionStat", {}).get("timeObstructed"), 2),
        icon="mdi:timer-sand",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_last_restart",
        name="Starlink Last Restart",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: (
            starlink_uptime_to_stable_datetime(_starlink(x)["deviceState"]["uptime"])
            if _starlink(x).get("deviceState", {}).get("uptime") is not None
            else None
        ),
        icon="mdi:clock-start",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_boot_count",
        name="Starlink Boot Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _starlink(x).get("deviceInfo", {}).get("bootCount"),
        icon="mdi:restart",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_software_version",
        name="Starlink Software Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _starlink(x).get("deviceInfo", {}).get("softwareVersion"),
        attributes_fn=lambda x: {
            "dish_id": _starlink(x).get("deviceInfo", {}).get("id"),
            "hardware_version": _starlink(x).get("deviceInfo", {}).get("hardwareVersion"),
            "mobility_class": _starlink(x).get("deviceInfo", {}).get("mobilityClass"),
        },
        icon="mdi:package-variant-closed",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_azimuth",
        name="Starlink Azimuth",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _starlink(x).get("alignmentStat", {}).get("boresightAzimuthDeg"),
        attributes_fn=lambda x: {
            "desired": _starlink(x).get("alignmentStat", {}).get("desiredBoresightAzimuthDeg"),
        },
        icon="mdi:compass-outline",
    ),
    PeplinkSensorEntityDescription(
        key="starlink_elevation",
        name="Starlink Elevation",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _starlink(x).get("alignmentStat", {}).get("boresightElevationDeg"),
        attributes_fn=lambda x: {
            "desired": _starlink(x).get("alignmentStat", {}).get("desiredBoresightElevationDeg"),
        },
        icon="mdi:angle-acute",
    ),
)

# Per-WAN sensors for a cellular WAN; signal values are those of the serving cell
CELLULAR_SENSOR_TYPES: tuple[PeplinkSensorEntityDescription, ...] = (
    PeplinkSensorEntityDescription(
        key="cellular_signal_level",
        name="Signal Level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _cellular(x).get("signalLevel"),
        icon="mdi:signal-cellular-3",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_rsrp",
        name="RSRP",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _primary_band(x).get("signal", {}).get("rsrp"),
        icon="mdi:signal",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_rsrq",
        name="RSRQ",
        native_unit_of_measurement="dB",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _primary_band(x).get("signal", {}).get("rsrq"),
        icon="mdi:signal",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_sinr",
        name="SINR",
        native_unit_of_measurement="dB",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _primary_band(x).get("signal", {}).get("sinr"),
        icon="mdi:signal",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_rssi",
        name="RSSI",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: _primary_band(x).get("signal", {}).get("rssi"),
        icon="mdi:signal",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_band",
        name="Band",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _primary_band(x).get("name"),
        attributes_fn=lambda x: {
            "channel": _primary_band(x).get("channel"),
            "pci": _primary_band(x).get("pci"),
            "channel_width": _primary_band(x).get("channelWidth"),
        },
        icon="mdi:radio-tower",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_technology",
        name="Network Technology",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _cellular(x).get("dataTechnology") or _cellular(x).get("mobileType") or None,
        icon="mdi:network-strength-4",
    ),
    PeplinkSensorEntityDescription(
        key="cellular_carrier",
        name="Carrier",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda x: _cellular(x).get("carrier", {}).get("name") or None,
        icon="mdi:sim",
    ),
)

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
            uptime_to_stable_datetime(x.get("uptime"))
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
    # GPS Location sensors
    PeplinkSensorEntityDescription(
        key="heading",
        translation_key=None,
        name="Heading",
        native_unit_of_measurement="°",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get('heading'),
        icon="mdi:compass",
    ),
    PeplinkSensorEntityDescription(
        key="speed",
        translation_key=None,
        name="Speed",
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get('speed'),
        icon="mdi:speedometer",
    ),
    PeplinkSensorEntityDescription(
        key="altitude",
        translation_key=None,
        name="Altitude",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda x: x.get('altitude'),
        icon="mdi:arrow-up-bold",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Peplink sensors."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    if entry_data.get("kind") == "ap_one":
        async_add_entities(ap_one_sensor_entities(entry_data["coordinator"]))
        return
    coordinator = entry_data["coordinator"]

    entities = []

    # Add system sensors
    thermal_sensors = coordinator.data.get("thermal_sensors", {})
    if thermal_sensors and thermal_sensors.get("sensors"):
        sensor = thermal_sensors["sensors"][0]  # Only one sensor
        for description in SENSOR_TYPES:
            if description.key in ["system_temperature", "system_temperature_threshold"]:
                if description.key == "system_temperature_threshold" and sensor.get("threshold") is None:
                    continue
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
                name=f"{coordinator.device_name or 'Peplink'} WAN{wan_id}",
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
                    if description.key.startswith("wan_") and description.key not in ["wan_download_rate", "wan_upload_rate", "wan_message", "wan_uptime", "wan_up_since"]:
                        # Create a copy of the description for this specific WAN
                        sensor_description = PeplinkSensorEntityDescription(
                            key=description.key.replace("wan_", ""),
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
                        
                # Handle uptime - if available in data
                if "uptime" in wan_connection:
                    uptime_description = next(
                        (d for d in SENSOR_TYPES if d.key == "wan_up_since"), None
                    )
                    if uptime_description:
                        sensor_description = PeplinkSensorEntityDescription(
                            key=uptime_description.key.replace("wan_", ""),
                            translation_key=uptime_description.translation_key,
                            name=uptime_description.name,
                            native_unit_of_measurement=uptime_description.native_unit_of_measurement,
                            device_class=uptime_description.device_class,
                            state_class=uptime_description.state_class,
                            icon=uptime_description.icon,
                            value_fn=uptime_description.value_fn,
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

                # Starlink dish sensors for a WAN the router reports as Starlink
                extra_descriptions: tuple[PeplinkSensorEntityDescription, ...] = ()
                if "starlink" in wan_connection or wan_connection.get("virtualType") == "starlink":
                    extra_descriptions += STARLINK_SENSOR_TYPES
                # Signal sensors for a cellular WAN whose module reports signal data
                cellular = _cellular(wan_connection)
                if "signalLevel" in cellular or "rat" in cellular:
                    extra_descriptions += CELLULAR_SENSOR_TYPES
                for description in extra_descriptions:
                    entities.append(
                        PeplinkWANSensor(
                            coordinator=coordinator,
                            description=description,
                            sensor_data=wan_connection,
                            device_info=device_info,
                            wan_id=wan_id,
                        )
                    )

    # CPU load and last restart, and PoE power per port (SD switches report these)
    entities.extend(_system_stats_sensors(coordinator))
    entities.extend(_poe_power_sensors(coordinator))

    # Add GPS location sensors
    location_info = coordinator.data.get("location_info", {})
    has_gps = location_info.get("gps", False)
    _LOGGER.debug("GPS capability check: %s (has_gps=%s)", location_info, has_gps)
    
    if has_gps:
        location_data = location_info.get("location", {})
        if location_data:
            for description in SENSOR_TYPES:
                if description.key in ["heading", "speed", "altitude"]:
                    entities.append(
                        PeplinkSensor(
                            coordinator=coordinator,
                            description=description,
                            sensor_data=location_data,
                        )
                    )
            _LOGGER.debug("Added GPS sensors for heading, speed, and altitude")
        else:
            _LOGGER.debug("Router has GPS capability but no valid location data")
    else:
        _LOGGER.debug("Router does not have GPS capability - skipping GPS sensors")

    # Add all entities
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
        elif description.key in ["heading", "speed", "altitude"]:
            self._sensor_data_key = "location_info"
            
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
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        value = None
        
        if self.coordinator.data:
            # Handle location data differently
            if self.entity_description.key in ["heading", "speed", "altitude"]:
                location_data = self.coordinator.data.get("location_info", {}).get("location", {})
                if location_data and self.entity_description.value_fn:
                    value = self.entity_description.value_fn(location_data)
            # Handle system-level bandwidth sensors
            elif self.entity_description.key.startswith("system_") and self.entity_description.key in ["system_download_rate", "system_upload_rate"]:
                raw_traffic_data = self.coordinator.data.get("traffic_stats", {}).get("stats", [])
                if raw_traffic_data and self.entity_description.value_fn:
                    # Prepare system-level traffic data
                    system_traffic_data = {
                        "rx_rate": 0,
                        "tx_rate": 0,
                    }
                    # Sum up all WAN interfaces data
                    for wan in raw_traffic_data:
                        system_traffic_data["rx_rate"] += wan.get("rx_rate", 0)
                        system_traffic_data["tx_rate"] += wan.get("tx_rate", 0)

                    value = self.entity_description.value_fn(system_traffic_data)
            # Check if we need to extract from a specific data category
            elif self._sensor_data_key:
                # Handle thermal sensors
                if self._sensor_data_key == "thermal_sensors":
                    sensors = self.coordinator.data.get("thermal_sensors", {}).get("sensors", [])
                    for sensor in sensors:
                        if sensor.get("name") == self._sensor_data_id:
                            if self.entity_description.value_fn:
                                value = self.entity_description.value_fn(sensor)
                            break
                # Handle fan speeds
                elif self._sensor_data_key == "fan_speeds":
                    fans = self.coordinator.data.get("fan_speeds", {}).get("fans", [])
                    for i, fan in enumerate(fans, 1):
                        if str(i) == str(self._sensor_data_id):
                            if self.entity_description.value_fn:
                                value = self.entity_description.value_fn(fan)
                            break
                # Handle device info
                elif self._sensor_data_key == "device_info":
                    device_info = self.coordinator.data.get("device_info", {})
                    if device_info and self.entity_description.value_fn:
                        value = self.entity_description.value_fn(device_info)
            # Handle sensors with no specific data category
            elif self.entity_description.value_fn:
                value = self.entity_description.value_fn(self._initial_sensor_data)
        
        # Fallback to initial data if no value found
        if value is None and self.entity_description.value_fn:
            value = self.entity_description.value_fn(self._initial_sensor_data)
            
        return value


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
        
        # Use device name as the prefix for consistent entity IDs
        self._attr_unique_id = f"{coordinator.device_name or coordinator.host}_wan{wan_id}_{description.key}"
        
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
        if self.entity_description.attributes_fn is not None:
            if self.coordinator.data:
                connections = self.coordinator.data.get("wan_status", {}).get("connection", [])
                for connection in connections:
                    if str(connection.get("id", "")) == self._wan_id:
                        return self.entity_description.attributes_fn(connection)
            return self.entity_description.attributes_fn(self._initial_sensor_data)
        return self._extra_attrs


def _system_stats_sensors(coordinator: PeplinkDataUpdateCoordinator) -> list[SensorEntity]:
    """Create CPU load and last restart sensors when the device reports them."""
    stats = (coordinator.data or {}).get("system_stats") or {}
    entities: list[SensorEntity] = []
    if stats.get("cpu_load") is not None:
        entities.append(
            PeplinkDataSensor(
                coordinator,
                PeplinkSensorEntityDescription(
                    key="cpu_load",
                    name="CPU Load",
                    native_unit_of_measurement=PERCENTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    value_fn=lambda d: (d.get("system_stats") or {}).get("cpu_load"),
                    icon="mdi:cpu-64-bit",
                ),
            )
        )
    if stats.get("uptime") is not None:
        entities.append(
            PeplinkDataSensor(
                coordinator,
                PeplinkSensorEntityDescription(
                    key="last_restart",
                    name="Last Restart",
                    device_class=SensorDeviceClass.TIMESTAMP,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    value_fn=lambda d: (
                        device_uptime_to_stable_datetime(d["system_stats"]["uptime"])
                        if (d.get("system_stats") or {}).get("uptime") is not None
                        else None
                    ),
                    icon="mdi:clock-start",
                ),
            )
        )
    return entities


def _poe_power(data: dict | None, port_id: str) -> float | None:
    """Return the PoE power draw of a LAN port in watts, or None if it reports none."""
    port = ((data or {}).get("port_status") or {}).get("lan", {}).get(port_id)
    poe = port.get("poe") if isinstance(port, dict) else None
    power = poe.get("power") if isinstance(poe, dict) else None
    return power.get("value") if isinstance(power, dict) else None


def _poe_power_sensors(coordinator: PeplinkDataUpdateCoordinator) -> list[SensorEntity]:
    """Create a PoE power sensor per LAN port that reports its draw."""
    lan = ((coordinator.data or {}).get("port_status") or {}).get("lan", {})
    entities: list[SensorEntity] = []
    for port_id in lan.get("order", []):
        port_id = str(port_id)
        if _poe_power(coordinator.data, port_id) is None:
            continue
        entities.append(
            PeplinkDataSensor(
                coordinator,
                PeplinkSensorEntityDescription(
                    key=f"lan_port_{port_id}_poe_power",
                    name=f"LAN Port {port_id} PoE Power",
                    native_unit_of_measurement=UnitOfPower.WATT,
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    value_fn=lambda d, p=port_id: _poe_power(d, p),
                    icon="mdi:flash",
                ),
            )
        )
    return entities


class PeplinkDataSensor(CoordinatorEntity, SensorEntity):
    """A device-level sensor whose value is computed from the whole coordinator data."""

    entity_description: PeplinkSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeplinkDataUpdateCoordinator,
        description: PeplinkSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.config_entry.entry_id)})
        if description.icon:
            self._attr_icon = description.icon

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data or {})


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
