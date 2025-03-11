"""Constants for the Peplink Local integration."""

DOMAIN = "peplink_local"

# Configuration
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"

# Default values
SCAN_INTERVAL = 60  # seconds

# Entity attributes
ATTR_WAN_ID = "wan_id"
ATTR_WAN_NAME = "wan_name"
ATTR_CLIENT_NAME = "client_name"
ATTR_CLIENT_MAC = "mac_address"
ATTR_CLIENT_IP = "ip_address"
