"""Button platform for Peplink Local: reboots and Starlink commands (admin login only)."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PeplinkDataUpdateCoordinator
from .const import DOMAIN
from .entity import (
    async_send_command,
    has_cellular_signal,
    is_starlink,
    router_device_info,
    wan_device_info,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PeplinkButtonEntityDescription(ButtonEntityDescription):
    """Describes a Peplink command button."""

    func: str = ""
    payload: dict[str, Any] | None = None


ROUTER_BUTTONS: tuple[PeplinkButtonEntityDescription, ...] = (
    PeplinkButtonEntityDescription(
        key="reboot",
        name="Reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        func="cmd.system.reboot",
    ),
)

# cmd.starlink needs an active Care plan on the router; without one it answers "fail"
STARLINK_BUTTONS: tuple[PeplinkButtonEntityDescription, ...] = (
    PeplinkButtonEntityDescription(
        key="starlink_reboot",
        name="Starlink Reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:satellite-variant",
        func="cmd.starlink",
        payload={"action": "reboot"},
    ),
    PeplinkButtonEntityDescription(
        key="starlink_stow",
        name="Starlink Stow",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:arrow-collapse-down",
        func="cmd.starlink",
        payload={"action": "stow"},
    ),
    PeplinkButtonEntityDescription(
        key="starlink_unstow",
        name="Starlink Unstow",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:arrow-expand-up",
        func="cmd.starlink",
        payload={"action": "unstow"},
    ),
)

CELLULAR_BUTTONS: tuple[PeplinkButtonEntityDescription, ...] = (
    PeplinkButtonEntityDescription(
        key="cellular_module_reset",
        name="Reset Cellular Module",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        func="cmd.cellularModule.reset",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Peplink buttons; none without an admin login."""
    coordinator: PeplinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if not coordinator.is_admin:
        return

    entities: list[ButtonEntity] = [
        PeplinkButton(coordinator, description, router_device_info(coordinator), None)
        for description in ROUTER_BUTTONS
    ]

    for connection in (coordinator.data or {}).get("wan_status", {}).get("connection", []):
        wan_id = str(connection.get("id", ""))
        descriptions: tuple[PeplinkButtonEntityDescription, ...] = ()
        if is_starlink(connection):
            descriptions += STARLINK_BUTTONS
        if has_cellular_signal(connection):
            descriptions += CELLULAR_BUTTONS
        for description in descriptions:
            entities.append(
                PeplinkButton(coordinator, description, wan_device_info(coordinator, wan_id), wan_id)
            )

    async_add_entities(entities)


class PeplinkButton(CoordinatorEntity, ButtonEntity):
    """A button that sends one command to the router, optionally for one WAN."""

    entity_description: PeplinkButtonEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PeplinkDataUpdateCoordinator,
        description: PeplinkButtonEntityDescription,
        device_info: DeviceInfo,
        wan_id: str | None,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._wan_id = wan_id
        scope = f"wan{wan_id}_" if wan_id is not None else ""
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{scope}{description.key}_button"
        self._attr_device_info = device_info

    async def async_press(self) -> None:
        """Send the command."""
        payload = dict(self.entity_description.payload or {})
        if self._wan_id is not None:
            payload["connId"] = int(self._wan_id)
        await async_send_command(self.coordinator, self.entity_description.func, payload)
