"""Data update coordinator for the Run-Chicken integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_register_callback,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .run_chicken_ble.models import RunChickenDeviceData

if TYPE_CHECKING:
    from bleak import BleakGATTCharacteristic
    from homeassistant.components.bluetooth import (
        BluetoothChange,
        BluetoothServiceInfoBleak,
    )
    from homeassistant.core import HomeAssistant

    from . import RunChickenConfigEntry
    from .run_chicken_ble.parser import RunChickenDevice

_LOGGER = logging.getLogger(__name__)


class RunChickenCoordinator(DataUpdateCoordinator[RunChickenDeviceData]):
    """Coordinate updates for a Run-Chicken door and own its BLE event wiring."""

    config_entry: RunChickenConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RunChickenConfigEntry, device: RunChickenDevice) -> None:
        """Initialize the coordinator for a single Run-Chicken device."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.device = device

    async def async_init(self) -> None:
        """Connect, subscribe to notifications, and wire up reconnect handling."""
        # Reconnect on an unexpected disconnect; the closure reads the callback
        # at disconnect time, so setting it before the first refresh is fine.
        self.device.set_disconnect_callback(self._schedule_reconnect)

        await self.async_config_entry_first_refresh()

        await self.device.register_notification_callback(self._handle_notification)

        # Refresh when the door advertises again (e.g. after dropping the link).
        self.config_entry.async_on_unload(
            async_register_callback(
                self.hass,
                self._handle_bluetooth_event,
                BluetoothCallbackMatcher(address=self.device.address),
                BluetoothScanningMode.ACTIVE,
            )
        )

    async def _async_update_data(self) -> RunChickenDeviceData:
        """Fetch the latest door state over BLE (also reconnects if needed)."""
        _LOGGER.debug("Polling Run-Chicken device %s", self.device.address)
        return await self.device.update_device()

    def _handle_notification(self, _gatt_char: BleakGATTCharacteristic, payload: bytearray) -> None:
        """Push a device notification payload into the coordinator."""
        _LOGGER.debug("Handling notification payload")
        self.async_set_updated_data(self.device.update_device_from_bytes(payload))

    # BluetoothChange is a functional Enum (Enum("BluetoothChange", ...)) that
    # PyCharm can't use as a type annotation, though the hint is correct for ty.
    # noinspection PyTypeHints
    def _handle_bluetooth_event(self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
        """Refresh on a Bluetooth advertisement (reconnects and re-subscribes)."""
        _LOGGER.debug("BLE event received: %s, change %s", service_info, change)
        self.hass.async_create_task(self.async_request_refresh(), f"{DOMAIN}_advertisement_refresh")

    def _schedule_reconnect(self) -> None:
        """Reconnect after an unexpected disconnect so push updates resume."""
        _LOGGER.debug("Run-Chicken %s disconnected; scheduling reconnect", self.device.address)
        self.hass.async_create_task(self.async_request_refresh(), f"{DOMAIN}_reconnect")
