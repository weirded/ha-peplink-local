# Home Assistant Peplink Local Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

This custom integration allows you to monitor and track your Peplink router from Home Assistant. It uses the local Peplink API to provide sensors for WAN connections and device tracking capabilities.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=weirded&repository=ha-peplink-local&category=integration)

## Features

- **Local Communication**: Communicates directly with your Peplink router over your local network
- **WAN Status Sensors**: 
  - Connection Status (connectivity sensor)
  - Download Rate (data rate sensor)
  - Upload Rate (data rate sensor)
  - WAN Type (text sensor)
  - WAN Name (text sensor)
  - WAN IP Address (text sensor)
  - WAN Up Since (timestamp sensor)
- **Router Sensors**:
  - Fan Speed Sensors (speed sensors, dynamically created for each fan)
  - System Temperature (temperature sensor)
  - System Temperature Threshold (temperature sensor) 
  - Serial Number (diagnostic sensor)
  - Device Name (diagnostic sensor)
  - Firmware Version (diagnostic sensor)
- **Device Tracking**: Tracks client devices connected to your Peplink router
- **Traffic Statistics**:
  - WAN Download (data rate sensor)
  - WAN Upload (data rate sensor)
  - Total Download (data rate sensor)
  - Total Upload (data rate sensor)
- **Configurable Polling**: Adjust how frequently the integration polls your router (default: 5 seconds)

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
   - **Polling Frequency** (optional): How often to poll the router for updates (in seconds, default: 5)
4. Click "Submit"

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit a pull request or open an issue on the [GitHub repository](https://github.com/weirded/ha-peplink-local).

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

[releases-shield]: https://img.shields.io/github/release/weirded/ha-peplink-local.svg?style=for-the-badge
[releases]: https://github.com/weirded/ha-peplink-local/releases
[license-shield]: https://img.shields.io/github/license/weirded/ha-peplink-local.svg?style=for-the-badge
