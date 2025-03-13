"""The Peplink Local integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .peplink_api import PeplinkAPI, PeplinkAuthFailed

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER, Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Peplink Local component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Peplink Local from a config entry."""
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)

    api = PeplinkAPI(
        host=host,
        username=username,
        password=password,
        session=session,
        verify_ssl=verify_ssl,
    )

    try:
        if not await api.connect():
            raise ConfigEntryAuthFailed("Failed to connect to Peplink router")

        coordinator = PeplinkDataUpdateCoordinator(
            hass=hass,
            logger=_LOGGER,
            name=f"Peplink {host}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
            api=api,
            config_entry=entry,
        )

        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": coordinator,
            "api": api,
        }

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Peplink Router ({host})",
            manufacturer="Peplink",
            model="Router",
        )

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except PeplinkAuthFailed as err:
        raise ConfigEntryAuthFailed from err
    except Exception as err:
        _LOGGER.exception("Error setting up Peplink integration")
        raise ConfigEntryNotReady(f"Failed to connect: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        api = data["api"]
        await api.close()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


class PeplinkDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        name: str,
        update_interval: timedelta,
        api: PeplinkAPI,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.api = api
        self.config_entry = config_entry
        self.host = config_entry.data[CONF_HOST]
        self.model = "Router"  # Can be updated later if the API provides model info
        self.firmware = "Unknown"  # Can be updated later if the API provides firmware info

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API."""
        try:
            # Ensure we're connected
            if not await self.api.ensure_connected():
                raise UpdateFailed("Failed to connect to Peplink router")

            # Parallelize API calls using asyncio.gather
            results = await asyncio.gather(
                self.api.get_wan_status(),
                self.api.get_clients(),
                self.api.get_thermal_sensors(),
                self.api.get_fan_speeds(),
                self.api.get_traffic_stats(),
                return_exceptions=True,
            )
            
            # Check results for exceptions
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    api_calls = ["WAN status", "client information", "thermal sensor data", 
                                "fan speed data", "traffic statistics"]
                    raise UpdateFailed(f"Failed to get {api_calls[i]}: {result}")
                
            # Unpack results
            wan_status, clients, thermal_sensors, fan_speeds, traffic_stats = results
            
            # Validate results
            if not wan_status:
                raise UpdateFailed("Failed to get WAN status")
            if not clients:
                raise UpdateFailed("Failed to get client information")
            if not thermal_sensors:
                raise UpdateFailed("Failed to get thermal sensor data")
            if not fan_speeds:
                raise UpdateFailed("Failed to get fan speed data")
            if not traffic_stats:
                raise UpdateFailed("Failed to get traffic statistics")

            return {
                "wan_status": wan_status,
                "clients": clients,
                "thermal_sensors": thermal_sensors,
                "fan_speeds": fan_speeds,
                "traffic_stats": traffic_stats,
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
