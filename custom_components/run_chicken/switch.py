"""Switch platform for run_chicken."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .run_chicken_ble.models import RunChickenMotorMode

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry
    from .coordinator import RunChickenCoordinator

_NOT_SUPPORTED_MSG = "Setting motor mode from Home Assistant isn't supported yet - change it in the Run-Chicken app for now."


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken motor-mode switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RunChickenMotorModeSwitch(
                coordinator, "anti_pinch", "Anti-pinch", RunChickenMotorMode.ANTI_PINCH, "mdi:hand-back-right"
            ),
            RunChickenMotorModeSwitch(
                coordinator, "power_mode", "Power-mode", RunChickenMotorMode.POWER_MODE, "mdi:engine"
            ),
        ]
    )


class RunChickenMotorModeSwitch(CoordinatorEntity["RunChickenCoordinator"], SwitchEntity):
    """
    Mirrors one of the door's two mutually-exclusive motor-mode toggles, matching the app's own UI.

    The app exposes Anti-pinch and Power-mode as two separate switches even
    though the door itself reports a single selector (see
    ``RunChickenMotorMode``) - this mirrors that same one-switch-per-mode
    shape here. Read-only for now: the door's write command for changing
    motor mode hasn't been reverse-engineered yet, so toggling either switch
    raises rather than silently doing nothing.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RunChickenCoordinator,
        key: str,
        name: str,
        mode: RunChickenMotorMode,
        icon: str,
    ) -> None:
        """Initialize the switch for a single motor mode."""
        super().__init__(coordinator)
        self._mode = mode
        self.run_chicken_device = coordinator.device
        self._attr_unique_id = f"run_chicken_{self.run_chicken_device.address}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self.run_chicken_device.address)},
            name=self.run_chicken_device.name,
            manufacturer=self.run_chicken_device.manufacturer,
            model=self.run_chicken_device.model,
        )

    @property
    def is_on(self) -> bool:
        """Return whether the door's current motor mode matches this switch's mode."""
        return self.coordinator.data.motor_mode is self._mode

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Not yet supported - the door's set-motor-mode write command hasn't been decoded."""
        raise HomeAssistantError(_NOT_SUPPORTED_MSG)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Not yet supported - the door's set-motor-mode write command hasn't been decoded."""
        raise HomeAssistantError(_NOT_SUPPORTED_MSG)
