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

from .peplink_api import PeplinkAPI
from .const import DOMAIN, CONF_VERIFY_SSL, SCAN_INTERVAL

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
            _LOGGER.exception("Error fetching data from Peplink router: %s", e)
            return {
                "wan": {"connection": []},
                "clients": {"client": []}
            }

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Peplink Router ({host})",
        update_method=async_update_data,
        update_interval=timedelta(seconds=SCAN_INTERVAL),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator and client for use by the platforms
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "session": session,
        "verify_ssl": verify_ssl,
    }

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for config entry changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


def _create_insecure_ssl_context():
    """Create an insecure SSL context (non-blocking function)."""
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Get the client and close it
        client = hass.data[DOMAIN][entry.entry_id]["client"]
        await client.close()
        
        # If we created a custom session, close it
        if not hass.data[DOMAIN][entry.entry_id]["verify_ssl"]:
            session = hass.data[DOMAIN][entry.entry_id]["session"]
            await session.close()
        
        # Remove the entry from hass.data
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # If this was the last entry, remove the domain
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
