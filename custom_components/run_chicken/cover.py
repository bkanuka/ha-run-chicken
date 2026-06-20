"""Cover platform for run_chicken."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
)
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RunChickenCoordinator
from .run_chicken_ble.models import RunChickenDoorState

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry

ENTITY_DESCRIPTIONS = CoverEntityDescription(
    key="run_chicken",
    name="Run Chicken Cover",
    device_class=CoverDeviceClass.DOOR,
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken cover control."""
    coordinator = entry.runtime_data
    _LOGGER.debug("Setting up Run-Chicken cover with data: %s", coordinator.data)
    async_add_entities([RunChickenCoverEntity(coordinator)])


class RunChickenCoverEntity(CoordinatorEntity[RunChickenCoordinator], CoverEntity):
    """Run Chicken Cover."""

    _attr_device_class = CoverDeviceClass.DOOR

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the Run-Chicken cover."""
        super().__init__(coordinator)
        self.run_chicken_device = coordinator.device

        self._attr_unique_id = f"run_chicken_{self.run_chicken_device.address}"

        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    self.run_chicken_device.address,
                )
            },
            name=self.run_chicken_device.device_data.name,
            manufacturer=self.run_chicken_device.device_data.manufacturer,
            model=self.run_chicken_device.device_data.model,
        )

    @property
    def is_closed(self) -> bool | None:
        """Return None if status is unknown, True if closed, else False."""
        if self.coordinator.data.door_state is RunChickenDoorState.UNKNOWN:
            return None
        return self.coordinator.data.door_state is RunChickenDoorState.CLOSED

    async def async_open_cover(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Open the coop door (the device reconnects first if needed)."""
        await self.run_chicken_device.async_open()

    async def async_close_cover(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Close the coop door (the device reconnects first if needed)."""
        await self.run_chicken_device.async_close()

    def _handle_coordinator_update(self) -> None:
        """Handle data update."""
        _LOGGER.debug("Received data update from coordinator: %s", self.coordinator.data)
        self._attr_is_closed = self.coordinator.data.door_state is RunChickenDoorState.CLOSED
        self.async_write_ha_state()
