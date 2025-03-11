# Peplink Local Integration for Home Assistant

This custom integration allows you to monitor and track your Peplink router from Home Assistant. It uses the local Peplink API to provide sensors for WAN connections and device tracking capabilities.

## Features

- **WAN Status Sensors**: Creates a text sensor for each WAN connection showing its current status
- **Device Tracking**: Tracks client devices connected to your Peplink router
- **Local Communication**: Communicates directly with your Peplink router over your local network

## Requirements

- A Peplink router running firmware 8.1.1 or later
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
4. Click "Submit"

The integration will automatically:
1. Register a client with your Peplink router
2. Generate API credentials (client ID and client secret)
3. Obtain an access token
4. Create sensors for each WAN connection
5. Set up device tracking for connected clients

## API Documentation

This integration is based on the [Peplink Router API Documentation for Firmware 8.1.1](https://download.peplink.com/resources/Peplink-Router-API-Documentation-for-Firmware-8.1.1.pdf).

## Troubleshooting

If you encounter issues with the integration:

1. Check that your Peplink router is accessible at the configured IP address
2. Verify that your username and password are correct
3. Ensure your router is running firmware 8.1.1 or later
4. Check the Home Assistant logs for any error messages

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit a pull request or open an issue on the [GitHub repository](https://github.com/weirded/ha-peplink-local).

## License

This project is licensed under the MIT License - see the LICENSE file for details.
