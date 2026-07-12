"""Switch platform for run_chicken."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import RunChickenEntity
from .run_chicken_ble.models import RunChickenMotorMode

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry
    from .coordinator import RunChickenCoordinator

_NOT_SUPPORTED_MSG = "Setting motor mode from Home Assistant isn't supported for this door model - change it in the Run-Chicken app for now."


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


class RunChickenMotorModeSwitch(RunChickenEntity, SwitchEntity):
    """
    Mirrors one of the door's two mutually-exclusive motor-mode toggles, matching the app's own UI.

    The app exposes Anti-pinch and Power-mode as two separate switches even
    though the door itself reports a single selector (see
    ``RunChickenMotorMode``) - this mirrors that same one-switch-per-mode shape
    here. Turning one on turns the other off, because they are the same
    underlying selector; turning a switch off returns the selector to OFF only
    when that switch is the active mode.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: RunChickenCoordinator,
        key: str,
        name: str,
        mode: RunChickenMotorMode,
        icon: str,
    ) -> None:
        """Initialize the switch for a single motor mode."""
        super().__init__(coordinator, key)
        self._mode = mode
        self._attr_name = name
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        """Return whether the door's current motor mode matches this switch's mode."""
        return self.coordinator.data.motor_mode is self._mode

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Select this switch's motor mode (implicitly deselecting the other)."""
        if not self.run_chicken_device.protocol.supports_settings_write:
            raise HomeAssistantError(_NOT_SUPPORTED_MSG)
        await self._async_write_settings(motor_mode=self._mode)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Turn the motor mode off, but only if this switch is the active one."""
        if not self.run_chicken_device.protocol.supports_settings_write:
            raise HomeAssistantError(_NOT_SUPPORTED_MSG)
        # The two switches share one selector; only the active one owns "off",
        # so turning off the inactive switch must not clobber the other's mode.
        if self.coordinator.data.motor_mode is self._mode:
            await self._async_write_settings(motor_mode=RunChickenMotorMode.OFF)
