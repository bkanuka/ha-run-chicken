"""Time platform for run_chicken (open/close Timer times)."""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util
from homeassistant.components.time import TimeEntity

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
    """Set up the Run-Chicken open/close time controls."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RunChickenScheduleTime(coordinator, "open", "mdi:door-open"),
            RunChickenScheduleTime(coordinator, "close", "mdi:door-closed"),
        ]
    )


class RunChickenScheduleTime(RunChickenConditionallyVisibleEntity, TimeEntity):
    """
    The Timer open or close time, shown and set in local time.

    The door stores this time in UTC (Timer mode uses it directly; Sun modes
    resolve into it daily), so this entity converts to local time for display
    and back to UTC when set. Only meaningful in Timer mode, so it hides itself
    from default dashboards otherwise (like the time sensor). Off by default;
    enable it to set the Timer time from Home Assistant.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: RunChickenCoordinator,
        action: str,
        icon: str,
    ) -> None:
        """Initialize a time control for one direction ("open"/"close")."""
        super().__init__(coordinator, f"{action}_time")
        self._action = action
        self._attr_name = f"{action.title()} time"
        self._attr_icon = icon

    @property
    def _is_applicable(self) -> bool:
        """Return whether this time's schedule mode is currently Timer."""
        mode = getattr(self.coordinator.data, f"{self._action}_schedule_mode")
        return mode is RunChickenScheduleMode.TIMER

    @property
    def native_value(self) -> dt.time | None:
        """Return the door's UTC time converted to local time, or None."""
        utc_time: dt.time | None = getattr(self.coordinator.data, f"{self._action}_time")
        if utc_time is None:
            return None
        # combine() carries the time's UTC tzinfo onto the datetime.
        aware_utc = dt.datetime.combine(dt_util.utcnow().date(), utc_time)
        return dt_util.as_local(aware_utc).time()

    async def async_set_value(self, value: dt.time) -> None:
        """Convert the chosen local time to UTC and write it, preserving other settings."""
        aware_local = dt.datetime.combine(dt_util.now().date(), value, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        utc_time = dt_util.as_utc(aware_local).timetz()
        await self._async_write_settings(**{f"{self._action}_time": utc_time})
