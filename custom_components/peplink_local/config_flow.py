"""Config flow for Peplink Local integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .ap_one import DEFAULT_AP_ONE_POLL_FREQUENCY, async_probe_ap_one
from .const import (
    DOMAIN,
    CONF_COMMUNITY,
    CONF_DEVICE_TYPE,
    CONF_POLL_FREQUENCY,
    DEFAULT_COMMUNITY,
    DEFAULT_POLL_FREQUENCY,
    DEVICE_TYPE_AP_ONE,
)
from .peplink_api import PeplinkAPI, PeplinkAuthFailed, PeplinkSSLError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
        vol.Optional(CONF_POLL_FREQUENCY, default=DEFAULT_POLL_FREQUENCY): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=300)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    verify_ssl = data.get(CONF_VERIFY_SSL, True)

    # Get the session with appropriate SSL settings
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)

    try:
        # Test the connection
        client = PeplinkAPI(
            host=host,
            username=username,
            password=password,
            session=session,
            verify_ssl=verify_ssl
        )

        if not await client.connect():
            raise PeplinkAuthFailed
            
        # Attempt to get the device name
        device_info = await client.get_device_info()
        device_name = None
        if device_info and "device_info" in device_info:
            device_name = device_info["device_info"].get("name")
        if not device_name:
            # SD switches only answer the public /api/ form
            system_info = await client.get_system_info(public_api=True)
            device_name = system_info.get("device_info", {}).get("name")
            
    except PeplinkAuthFailed as err:
        raise PeplinkAuthFailed from err
    except PeplinkSSLError as err:
        # Catch and re-raise SSL errors separately
        raise PeplinkSSLError from err
    except Exception as e:
        _LOGGER.exception("Unexpected exception: %s", e)
        raise

    # Return info to be stored in the config entry
    # Use the device name if available, otherwise use the IP address
    if device_name:
        return {"title": device_name}
    else:
        return {"title": f"Peplink Router ({data[CONF_HOST]})"}


class PeplinkLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Peplink Local."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask which kind of Peplink device to add."""
        return self.async_show_menu(step_id="user", menu_options=["router", "ap_one"])

    async def async_step_ap_one(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add an AP One, which is read over SNMPv2c."""
        errors: dict[str, str] = {}
        defaults = user_input or {}
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_COMMUNITY, default=defaults.get(CONF_COMMUNITY, DEFAULT_COMMUNITY)): str,
            vol.Optional(
                CONF_POLL_FREQUENCY,
                default=defaults.get(CONF_POLL_FREQUENCY, DEFAULT_AP_ONE_POLL_FREQUENCY),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
        })
        if user_input is not None:
            try:
                data = await async_probe_ap_one(user_input[CONF_HOST], user_input[CONF_COMMUNITY])
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("AP One %s did not answer SNMP", user_input[CONF_HOST], exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                title = data["device"].get("hostname") or f"AP One ({user_input[CONF_HOST]})"
                return self.async_create_entry(
                    title=title, data={**user_input, CONF_DEVICE_TYPE: DEVICE_TYPE_AP_ONE}
                )
        return self.async_show_form(step_id="ap_one", data_schema=schema, errors=errors)

    async def async_step_router(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a router, FusionHub or SD Switch, which is read over its REST API."""
        errors: dict[str, str] = {}

        # Use user_input as defaults if provided, otherwise empty dict
        defaults = user_input or {}
        
        # Create a dynamic schema that uses the previous input as defaults
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Optional(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)): bool,
            vol.Optional(CONF_POLL_FREQUENCY, default=defaults.get(CONF_POLL_FREQUENCY, DEFAULT_POLL_FREQUENCY)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=300)
            ),
        })

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except PeplinkAuthFailed:
                errors["base"] = "invalid_auth"
            except PeplinkSSLError:
                errors["base"] = "ssl_error"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="router", data_schema=schema, errors=errors
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
                    vol.Optional(
                        CONF_POLL_FREQUENCY,
                        default=self.entry.data.get(CONF_POLL_FREQUENCY, DEFAULT_POLL_FREQUENCY),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
                }
            ),
        )
