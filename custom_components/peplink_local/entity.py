"""Shared helpers for Peplink Local entities that send commands to the router."""
from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN
from .peplink_api import PeplinkCommandError


def router_device_info(coordinator: PeplinkDataUpdateCoordinator) -> DeviceInfo:
    """Return device info that links an entity to the router device."""
    return DeviceInfo(identifiers={(DOMAIN, coordinator.config_entry.entry_id)})


def wan_device_info(coordinator: PeplinkDataUpdateCoordinator, wan_id: str) -> DeviceInfo:
    """Return device info for a WAN sub-device, matching the sensor platform's."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_wan{wan_id}")},
        manufacturer="Peplink",
        model="WAN Connection",
        name=f"{coordinator.device_name or 'Peplink'} WAN{wan_id}",
        via_device=(DOMAIN, coordinator.config_entry.entry_id),
    )


def wan_connection(data: dict[str, Any] | None, wan_id: str) -> dict[str, Any] | None:
    """Return one WAN connection from coordinator data, or None if it is gone."""
    for connection in (data or {}).get("wan_status", {}).get("connection", []):
        if str(connection.get("id", "")) == str(wan_id):
            return connection
    return None


def has_cellular_signal(connection: dict[str, Any]) -> bool:
    """Return True for a cellular WAN whose module reports signal data."""
    cellular = connection.get("cellular") or {}
    return "signalLevel" in cellular or "rat" in cellular


def is_starlink(connection: dict[str, Any]) -> bool:
    """Return True for a WAN the router reports as Starlink."""
    return "starlink" in connection or connection.get("virtualType") == "starlink"


async def async_send_command(
    coordinator: PeplinkDataUpdateCoordinator, func: str, data: dict[str, Any] | None = None
) -> None:
    """Send a command, surface a refusal as a Home Assistant error, then refresh."""
    try:
        await coordinator.api.send_command(func, data)
    except PeplinkCommandError as err:
        raise HomeAssistantError(str(err)) from err
    except Exception as err:  # pylint: disable=broad-except
        raise HomeAssistantError(f"{func} failed: {err}") from err
    await coordinator.async_request_refresh()
