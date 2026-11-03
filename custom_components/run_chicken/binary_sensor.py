"""Binary sensor platform for run_chicken."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RunChickenCoordinator
from .sensor import _device_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken binary sensors."""
    async_add_entities([RunChickenAntiPinchSensor(entry.runtime_data)])


class RunChickenAntiPinchSensor(CoordinatorEntity[RunChickenCoordinator], BinarySensorEntity):
    """Whether the door's anti-pinch (obstacle detection) is enabled (payload[41])."""

    _attr_has_entity_name = True
    _attr_translation_key = "anti_pinch"
    _attr_icon = "mdi:hand-back-left-off"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"run_chicken_{coordinator.device.address}_anti_pinch"
        self._attr_device_info = _device_info(coordinator)
        self._value: bool | None = None
        self._update_value()

    def _update_value(self) -> None:
        data = self.coordinator.data
        if data is not None and data.schedule is not None and data.schedule.anti_pinch is not None:
            self._value = data.schedule.anti_pinch

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value and write state."""
        self._update_value()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if anti-pinch is enabled."""
        return self._value
