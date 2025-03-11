"""The Peplink Local integration."""
import asyncio
import logging
import ssl
import aiohttp
from datetime import timedelta
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import async_get as async_get_device_registry

from .const import DOMAIN, CONF_VERIFY_SSL, SCAN_INTERVAL
from .peplink_api import PeplinkAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.DEVICE_TRACKER]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Peplink Local component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Peplink Local from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)

    hass.data.setdefault(DOMAIN, {})

    # Create a session with the appropriate SSL settings
    if not verify_ssl:
        # Create SSL context in a non-blocking way
        loop = asyncio.get_running_loop()
        ssl_context = await loop.run_in_executor(
            None, 
            partial(_create_insecure_ssl_context)
        )
        
        # Create a connector with the SSL context
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        # Create a session with a cookie jar and the custom connector
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        session = aiohttp.ClientSession(connector=connector, cookie_jar=cookie_jar)
    else:
        # Use the Home Assistant session
        session = async_get_clientsession(hass)

    # Create API client
    client = PeplinkAPI(
        router_ip=host, 
        username=username, 
        password=password, 
        session=session,
        verify_ssl=verify_ssl
    )

    # Test connection
    try:
        if not await client.connect():
            _LOGGER.error("Failed to connect to Peplink router")
            return False
    except Exception as e:
        _LOGGER.error("Error connecting to Peplink router: %s", e)
        return False

    async def async_update_data():
        """Fetch data from API endpoint."""
        try:
            # Get WAN status
            _LOGGER.debug("Fetching WAN status from Peplink router")
            wan_data = await client.get_wan_status()
            _LOGGER.debug("Received WAN data: %s", wan_data)
            
            # Get client information
            _LOGGER.debug("Fetching client information from Peplink router")
            client_data = await client.get_clients()
            _LOGGER.debug("Received client data: %s", client_data)
            
            # Check if we have valid data
            if (not wan_data or not wan_data.get("connection")) and (not client_data or not client_data.get("client")):
                _LOGGER.warning("No data received from Peplink router")
                # Return empty data structure to avoid errors
                return {
                    "wan": {"connection": []},
                    "clients": {"client": []}
                }
            
            # Return the data in the expected format
            return {
                "wan": wan_data,
                "clients": client_data
            }
            
        except Exception as e:
            _LOGGER.error("Error fetching data from Peplink router: %s", e)
            raise UpdateFailed(f"Error fetching data: {e}")

    # Create update coordinator
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{host}",
        update_method=async_update_data,
        update_interval=timedelta(seconds=SCAN_INTERVAL),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator and client in hass data
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    # Register the main router device
    device_registry = async_get_device_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Peplink Router ({host})",
        manufacturer="Peplink",
        model="Router",
    )

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _create_insecure_ssl_context():
    """Create an insecure SSL context (non-blocking function)."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Clean up resources
        if entry.entry_id in hass.data[DOMAIN]:
            client = hass.data[DOMAIN][entry.entry_id].get("client")
            if client:
                await client.close()
            
            # Remove the entry data
            hass.data[DOMAIN].pop(entry.entry_id)
            
            # If no more entries, remove the domain data
            if not hass.data[DOMAIN]:
                hass.data.pop(DOMAIN)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
