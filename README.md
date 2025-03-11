# Home Assistant Peplink Local Integration\

This custom integration allows you to monitor and track your Peplink router from Home Assistant. It uses the local Peplink API to provide sensors for WAN connections and device tracking capabilities.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=weirded&repository=ha-peplink-local&category=integration)

## Features

- **WAN Status Sensors**: 
  - Connection status (binary sensor)
  - WAN name (text sensor)
  - Connection message (text sensor)
  - IP address with gateway information (text sensor)
  - Connection type (text sensor)
  - Priority (numeric sensor)
  - Up since timestamp (timestamp sensor)
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

Additionally, device tracker entities are created for each client connected to your Peplink router.


## Data Refresh

The integration refreshes data from your Peplink router every 30 seconds.

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
