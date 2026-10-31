"""Select platform for Peplink Local: WAN priority (admin login only)."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN
from .entity import async_send_command, wan_connection, wan_device_info

_LOGGER = logging.getLogger(__name__)

PRIORITY_OPTIONS = ["1", "2", "3", "4"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up WAN priority selects; none without an admin login."""
    coordinator: PeplinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if not coordinator.is_admin:
        return

    async_add_entities(
        PeplinkWANPrioritySelect(coordinator, str(connection.get("id", "")))
        for connection in (coordinator.data or {}).get("wan_status", {}).get("connection", [])
        if connection.get("priority") is not None
    )


class PeplinkWANPrioritySelect(CoordinatorEntity, SelectEntity):
    """Sets a WAN's priority (POST config.wan.connection.priority, applied at once)."""

    _attr_has_entity_name = True
    _attr_name = "Priority"
    _attr_icon = "mdi:order-numeric-ascending"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = PRIORITY_OPTIONS

    def __init__(self, coordinator: PeplinkDataUpdateCoordinator, wan_id: str) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._wan_id = wan_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_wan{wan_id}_priority"
        self._attr_device_info = wan_device_info(coordinator, wan_id)

    @property
    def available(self) -> bool:
        """Return True while the router reports the WAN."""
        return super().available and wan_connection(self.coordinator.data, self._wan_id) is not None

    @property
    def current_option(self) -> str | None:
        """Return the WAN's current priority."""
        connection = wan_connection(self.coordinator.data, self._wan_id) or {}
        priority = str(connection.get("priority"))
        return priority if priority in PRIORITY_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        """Change the WAN's priority and apply it immediately."""
        await async_send_command(
            self.coordinator,
            "config.wan.connection.priority",
            {"instantActive": True, "list": [{"connId": int(self._wan_id), "priority": int(option)}]},
        )
