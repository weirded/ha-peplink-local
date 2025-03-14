# Peplink Local Integration for Home Assistant

This document tracks the features, implementation details, and development standards for the Home Assistant Peplink Local integration.

## Current Features and Implementation Details

### API Client
- Self-contained client for Peplink Router API
- Authentication via `/api/login` endpoint with cookie-based auth
- Proper SSL certificate validation handling
- Error handling with specific exceptions for auth and SSL failures

### Sensors
- **WAN Connection Sensors**:
  - Connection Status (binary sensor with connectivity device class)
  - Download Rate (in Mbit/s, rounded to 2 decimal places)
  - Upload Rate (in Mbit/s, rounded to 2 decimal places)
  - IP Address (with gateway, DNS, and subnet mask as attributes)
  - WAN Type (with friendly translations)
  - Up Since (timestamp showing when the connection was established)
  - Name

- **System Sensors**:
  - System Temperature
  - System Temperature Threshold

- **Device Tracking**:
  - Tracks clients connected to the router

### Implementation Details
- Data update coordinator using asyncio.gather() for parallel API requests
- Custom icons for all sensors with proper MDI icons
- Config flow with preserved input fields on validation failure
- Proper error handling for authentication and SSL errors

## Future Enhancements and Planned Features
- Bandwidth usage tracking
- Support for SpeedFusion status
- Outbound policy status and control
- Support for managing/viewing router traffic rules
- Integration with HA alerts for critical router events

## Known Issues and Feature Requests
- None currently

## Development Guidelines and Code Standards
- Follow Home Assistant development practices and guidelines
- Use type hints and mypy for type checking
- Use asyncio for async operations
- Use async/await for async functions
- Properly document all functions and classes
- Target Home Assistant versions 2025.1 and above
- Support Peplink routers version 8.1.1 and above
