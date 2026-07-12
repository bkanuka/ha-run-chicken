"""Number platform for run_chicken (sunrise/sunset schedule offsets)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime

from .entity import RunChickenConditionallyVisibleEntity
from .run_chicken_ble.models import RunChickenScheduleMode

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry
    from .coordinator import RunChickenCoordinator


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken open/close schedule-offset numbers."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RunChickenOffsetNumber(coordinator, "open", "mdi:sort-clock-ascending"),
            RunChickenOffsetNumber(coordinator, "close", "mdi:sort-clock-descending"),
        ]
    )


class RunChickenOffsetNumber(RunChickenConditionallyVisibleEntity, NumberEntity):
    """
    Minutes to offset the sunrise/sunset open or close time by.

    Only meaningful while the matching schedule is in Sunrise/Sunset mode, so
    it hides itself from default dashboards otherwise (like the offset sensor).
    Off by default; enable it to control the offset from Home Assistant. The
    app allows +/-60 minutes, but the byte encoding for negative offsets hasn't
    been confirmed, so this is limited to 0-60 for now.
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: RunChickenCoordinator,
        action: str,
        icon: str,
    ) -> None:
        """Initialize an offset number for one direction ("open"/"close")."""
        super().__init__(coordinator, f"{action}_offset_minutes")
        self._action = action
        self._attr_name = f"{action.title()} offset"
        self._attr_icon = icon

    @property
    def _is_applicable(self) -> bool:
        """Return whether this offset's schedule mode is currently Sunrise/Sunset."""
        mode = getattr(self.coordinator.data, f"{self._action}_schedule_mode")
        return mode is RunChickenScheduleMode.SUNRISE_SUNSET

    @property
    def native_value(self) -> float | None:
        """Return the current offset in minutes, or None if unknown."""
        value: int | None = getattr(self.coordinator.data, f"{self._action}_offset_minutes")
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write the chosen offset, preserving all other settings."""
        await self._async_write_settings(**{f"{self._action}_offset_minutes": int(value)})
