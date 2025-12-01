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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
)

from . import RunChickenDeviceData, RunChickenDevice
from .const import DOMAIN
from .run_chicken_ble.cover import RunChickenCover
from .run_chicken_ble.models import RunChickenDoorState

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, callback
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

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[RunChickenDeviceData],
        runchicken_device: RunChickenDeviceData,
        ble_device: BLEDevice,
    ) -> None:
        """Initialize an Thunderboard lights."""
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
        self._async_update_attrs()

    def _async_update_attrs(self) -> None:
        self._attr_is_closed = self.coordinator.data.door_state == RunChickenDoorState.CLOSED

    async def _get_controller(self):
        if self.controller is None or not self.controller.is_connected:
            self.controller = await RunChickenCover.from_ble_device(self.ble_device)
        return self.controller

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._get_controller()
        await self.controller.open_cover()
        print("coordinator data:", self.coordinator.data)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._get_controller()
        await self.controller.close_cover()
        print("coordinator data:", self.coordinator.data)


    def _handle_coordinator_update(self, *args: Any) -> None:
        """Handle data update."""
        _LOGGER.debug("Received update from coordinator")
        _LOGGER.debug(f"Coordinator data: {self.coordinator.data}")
        self._async_update_attrs()
        self.async_write_ha_state()
