"""Select platform for run_chicken (open/close schedule mode)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity

from .entity import RunChickenEntity
from .run_chicken_ble.models import RunChickenScheduleMode

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry
    from .coordinator import RunChickenCoordinator

_MANUAL = "manual"
_TIMER = "timer"


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken open/close schedule-mode selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RunChickenScheduleModeSelect(
                coordinator, "open_schedule_mode", "Open schedule", "sunrise", "mdi:weather-sunset-up"
            ),
            RunChickenScheduleModeSelect(
                coordinator, "close_schedule_mode", "Close schedule", "sunset", "mdi:weather-sunset-down"
            ),
        ]
    )


class RunChickenScheduleModeSelect(RunChickenEntity, SelectEntity):
    """
    Selects the open or close schedule mode: Manual, Sun (sunrise/sunset), or Timer.

    Backed by the door's single schedule-mode enum. The middle option is
    labelled per direction ("sunrise" for open, "sunset" for close) but maps to
    the same ``SUNRISE_SUNSET`` value the door uses for both.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: RunChickenCoordinator,
        field: str,
        name: str,
        sun_option: str,
        icon: str,
    ) -> None:
        """Initialize a schedule-mode select for one direction (open/close)."""
        super().__init__(coordinator, field)
        # Name of the RunChickenDeviceData field this control reads/writes.
        self._field = field
        self._sun_option = sun_option
        self._attr_name = name
        self._attr_icon = icon
        self._attr_options = [_MANUAL, sun_option, _TIMER]
        # Maps the door's enum to option strings, and back.
        self._to_option = {
            RunChickenScheduleMode.MANUAL: _MANUAL,
            RunChickenScheduleMode.SUNRISE_SUNSET: sun_option,
            RunChickenScheduleMode.TIMER: _TIMER,
        }
        self._to_mode = {option: mode for mode, option in self._to_option.items()}

    @property
    def current_option(self) -> str | None:
        """Return the current schedule mode as an option, or None if unknown."""
        mode: RunChickenScheduleMode = getattr(self.coordinator.data, self._field)
        return self._to_option.get(mode)

    async def async_select_option(self, option: str) -> None:
        """Write the chosen schedule mode, preserving all other settings."""
        await self._async_write_settings(**{self._field: self._to_mode[option]})
