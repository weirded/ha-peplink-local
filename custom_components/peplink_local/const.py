"""Constants for the Peplink Local integration."""

DOMAIN = "peplink_local"

# Configuration
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"
CONF_POLL_FREQUENCY = "poll_frequency"

# Defaults
DEFAULT_PORT = 443
DEFAULT_VERIFY_SSL = False
DEFAULT_POLL_FREQUENCY = 5  # seconds
SCAN_INTERVAL = 30  # seconds

# Attributes
ATTR_WAN_ID = "wan_id"
ATTR_CLIENT_NAME = "client_name"
ATTR_CLIENT_MAC = "mac_address"
ATTR_CLIENT_IP = "ip_address"
