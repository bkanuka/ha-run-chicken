"""Cover platform for run_chicken."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bleak import BLEDevice
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from .const import DOMAIN
from .run_chicken_ble.cover import RunChickenCover
from .run_chicken_ble.models import RunChickenDeviceData
from .run_chicken_ble.models import RunChickenDoorState

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

ENTITY_DESCRIPTIONS = (
    CoverEntityDescription(
        key="run_chicken",
        name="Run Chicken Cover",
        device_class=CoverDeviceClass.DOOR,
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken cover control."""
    address = entry.unique_id
    assert address is not None
    ble_device = async_ble_device_from_address(hass, address)
    coordinator: DataUpdateCoordinator[RunChickenDeviceData] = hass.data[DOMAIN][entry.entry_id]
    entities = []
    _LOGGER.debug("Got cover: %s", coordinator.data)

    entities.append(
        RunChickenCoverEntity(coordinator, coordinator.data, ble_device)
    )

    async_add_entities(entities)


class RunChickenCoverEntity(CoordinatorEntity[DataUpdateCoordinator[RunChickenDeviceData]], CoverEntity):
    """Run Chicken Cover."""

    _attr_device_class = CoverDeviceClass.DOOR

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[RunChickenDeviceData],
        runchicken_device: RunChickenDeviceData,
        ble_device: BLEDevice,
    ) -> None:
        """Initialize the Run-Chicken cover."""
        super().__init__(coordinator)
        self.ble_device = ble_device
        self.controller: RunChickenCover | None = None

        self._attr_unique_id = f"run_chicken_{runchicken_device.address}"

        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    runchicken_device.address,
                )
            },
            name=runchicken_device.name,
            manufacturer=runchicken_device.manufacturer,
            model=runchicken_device.model,
        )

    @property
    def is_closed(self) -> bool | None:
        """Return None if status is unknown, True if closed, else False."""
        if self.coordinator.data.door_state is RunChickenDoorState.UNKNOWN:
            return None
        if self.coordinator.data.door_state is RunChickenDoorState.CLOSED:
            return True
        return False

    async def _get_controller(self):
        if self.controller is None or not self.controller.is_connected:
            self.controller = await RunChickenCover.from_ble_device(self.ble_device)
        return self.controller

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._get_controller()
        await self.controller.open_cover()

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._get_controller()
        await self.controller.close_cover()

    def _handle_coordinator_update(self, *args: Any) -> None:
        """Handle data update."""
        _LOGGER.debug(f"Received data update from coordinator: {self.coordinator.data}")
        self._attr_is_closed = (self.coordinator.data.door_state is RunChickenDoorState.CLOSED)
        self.async_write_ha_state()
