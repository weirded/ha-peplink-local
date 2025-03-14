# Home Assistant Peplink Local Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

This custom integration allows you to monitor and track your Peplink router from Home Assistant. It uses the local Peplink API to provide sensors for WAN connections and device tracking capabilities.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=weirded&repository=ha-peplink-local&category=integration)

## Features

- **WAN Status Sensors**: 
  - System Temperature (temperature sensor)
  - System Temperature Threshold (temperature sensor)
  - Download Rate (data rate sensor)
  - Upload Rate (data rate sensor)
  - WAN Type (text sensor)
  - WAN Name (text sensor)
  - WAN IP Address (text sensor)
  - WAN Up Since (timestamp sensor)
- **Router Sensors**:
  - Fan Speed Sensors (speed sensors, dynamically created for each fan)
- **Binary Sensors**:
  - Connection Status (connectivity sensor)
- **Device Tracking**: Tracks client devices connected to your Peplink router
- **Local Communication**: Communicates directly with your Peplink router over your local network

## Requirements

- The router must be accessible on your local network
- Valid admin credentials for your Peplink router

## Installation

### HACS Installation (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Add this repository as a custom repository in HACS:
   - Go to HACS > Integrations > ⋮ > Custom repositories
   - Add `https://github.com/weirded/ha-peplink-local` as a repository
   - Select "Integration" as the category
3. Click "Install" on the Peplink Local integration
4. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [GitHub repository](https://github.com/weirded/ha-peplink-local)
2. Extract the `custom_components/peplink_local` directory into your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for "Peplink Local"
3. Enter the following information:
   - **IP Address**: The IP address of your Peplink router
   - **Username**: Admin username for your Peplink router
   - **Password**: Admin password for your Peplink router
   - **Verify SSL** (optional): Disable this if your router uses a self-signed certificate
4. Click "Submit"

The integration will automatically:
1. Connect to your Peplink router using the provided credentials
2. Create a device for your Peplink router
3. Create devices for each enabled WAN interface
4. Create sensors for each WAN interface with standardized naming (WAN1, WAN2, etc.)
5. Set up device tracking for connected clients

## Available Entities

For each enabled WAN interface (e.g., WAN1), the following entities are created:

| Entity | Type | Description |
|--------|------|-------------|
| `binary_sensor.wan1_connected` | Binary Sensor | Shows if the WAN interface is connected |
| `sensor.wan1_name` | Sensor | The configured name of the WAN interface |
| `sensor.wan1_message` | Sensor | Status message for the WAN interface |
| `sensor.wan1_ip` | Sensor | Current IP address of the WAN interface (includes gateway as attribute) |
| `sensor.wan1_connection_type` | Sensor | Type of connection (Ethernet, Cellular, etc.) |
| `sensor.wan1_priority` | Sensor | Priority of the WAN interface for routing |
| `sensor.wan1_up_since` | Timestamp | When the WAN interface was last connected/up since |
| `sensor.wan1_download_speed` | Data Rate | Current download speed in megabits per second |
| `sensor.wan1_upload_speed` | Data Rate | Current upload speed in megabits per second |

Additionally, the following router-specific sensors are created:

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.system_temperature` | Temperature | System temperature in degrees Celsius |
| `sensor.system_temperature_threshold` | Temperature | System temperature threshold in degrees Celsius |
| `sensor.fan_1_speed` | Speed | Speed of the first fan in RPM (if available) |
| `sensor.fan_2_speed` | Speed | Speed of the second fan in RPM (if available) |

Device tracker entities are also created for each client connected to your Peplink router.

## Data Refresh

The integration refreshes most data from your Peplink router every 30 seconds. 

However, the following data is refreshed more frequently (every 5 seconds):
- CPU temperature
- Fan speeds
- Download and upload speeds

This provides near real-time monitoring of system performance and network traffic.

## API Documentation

This integration is based on the [Peplink Router API Documentation for Firmware 8.1.1](https://download.peplink.com/resources/Peplink-Router-API-Documentation-for-Firmware-8.1.1.pdf).

## Troubleshooting

If you encounter issues with the integration:

1. Check that your Peplink router is accessible at the configured IP address
2. Verify that your username and password are correct
4. Check the Home Assistant logs for any error messages
5. If you see SSL errors, try disabling the "Verify SSL" option during setup

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit a pull request or open an issue on the [GitHub repository](https://github.com/weirded/ha-peplink-local).

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

[releases-shield]: https://img.shields.io/github/release/weirded/ha-peplink-local.svg?style=for-the-badge
[releases]: https://github.com/weirded/ha-peplink-local/releases
[license-shield]: https://img.shields.io/github/license/weirded/ha-peplink-local.svg?style=for-the-badge
