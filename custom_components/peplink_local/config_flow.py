"""Config flow for Peplink Local integration."""
import logging
import voluptuous as vol
import ssl
import aiohttp
import asyncio
from functools import partial

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_create_clientsession, async_get_clientsession

from .peplink_api import PeplinkAPI
from .const import DOMAIN, CONF_VERIFY_SSL

_LOGGER = logging.getLogger(__name__)


def _create_insecure_ssl_context():
    """Create an insecure SSL context (non-blocking function)."""
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


class PeplinkLocalFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Peplink Local."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            verify_ssl = user_input.get(CONF_VERIFY_SSL, True)

            # Check if already configured
            await self.async_set_unique_id(f"{host}")
            self._abort_if_unique_id_configured()

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
                # Use the Home Assistant session with default cookie jar
                session = async_get_clientsession(self.hass)

            # Test the connection
            client = PeplinkAPI(
                router_ip=host,
                username=username,
                password=password,
                session=session,
                verify_ssl=verify_ssl
            )

            try:
                if await client.connect():
                    # Connection successful, create entry
                    return self.async_create_entry(
                        title=f"Peplink Router ({host})",
                        data={
                            CONF_HOST: host,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_VERIFY_SSL: verify_ssl,
                        },
                    )
                else:
                    errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.exception("Unexpected exception: %s", e)
                errors["base"] = "unknown"
            finally:
                # Only close the session if we created it
                if not verify_ssl:
                    await session.close()

        # Show the form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_VERIFY_SSL, default=True): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return PeplinkLocalOptionsFlowHandler(config_entry)


class PeplinkLocalOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Peplink Local options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        # Don't directly set self.config_entry as it's deprecated
        self.entry = config_entry
        self.options = dict(config_entry.data)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Update the options
            return self.async_create_entry(title="", data=user_input)

        # Fill the form with current values
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_VERIFY_SSL,
                        default=self.entry.data.get(CONF_VERIFY_SSL, True),
                    ): bool,
                }
            ),
        )
