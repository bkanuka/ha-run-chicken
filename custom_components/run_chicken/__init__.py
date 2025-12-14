"""
Custom integration to integrate Run-Chicken with Home Assistant.

For more details about this integration, please refer to
https://github.com/bkanuka/ha-run-chicken
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakClient, BleakGATTCharacteristic
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_ble_device_from_address,
    async_register_callback,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .run_chicken_ble.parser import RunChickenDevice

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.components.bluetooth.models import (
        BluetoothChange,
        BluetoothServiceInfoBleak,
    )
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .run_chicken_ble.models import RunChickenDeviceData

PLATFORMS: list[Platform] = [
    Platform.COVER,
]

type RunChickenConfigEntry = ConfigEntry[RunChickenDevice]


async def async_setup_entry(hass: HomeAssistant, entry: RunChickenConfigEntry) -> bool:
    """Set up BLE device from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    address = entry.unique_id
    if address is None:
        msg = "No address found for Run-Chicken device."
        raise ConfigEntryNotReady(msg)

    ble_device = async_ble_device_from_address(hass, address, connectable=True)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.debug("Run-Chicken device address %s", address)
    run_chicken_device = RunChickenDevice(ble_device)

    # Forward the same Run-Chicken device instance to all platforms
    entry.runtime_data = run_chicken_device

    scan_interval = DEFAULT_SCAN_INTERVAL

    async def _async_update_method() -> RunChickenDeviceData:
        """Get data from Run-Chicken BLE."""
        _LOGGER.debug("Running Run-Chicken update method.")

        data: RunChickenDeviceData = await run_chicken_device.update_device()
        return data

    _LOGGER.debug("Polling interval is set to: %s seconds", scan_interval)

    # Create Coordinator
    coordinator = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_update_method,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Define and register a Bluetooth event callback to update the data when device start to advertise again
    def async_handle_bluetooth_event(service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
        """Handle a Bluetooth reconnect event."""
        _LOGGER.debug("BLE event received: %s, change %s", service_info, change)

        # Refresh data when device advertising is detected
        _LOGGER.debug("Require coordinator to update the data")
        loop = asyncio.get_running_loop()
        loop.create_task(coordinator.async_request_refresh())  # noqa: RUF006

    async_register_callback(
        hass,
        async_handle_bluetooth_event,
        BluetoothCallbackMatcher(address=address),
        BluetoothScanningMode.ACTIVE,
    )

    def notification_callback(gatt_char: BleakGATTCharacteristic, payload: bytearray) -> None:  # noqa: ARG001
        """Handle notification data from the device."""
        _LOGGER.debug("Handling notification payload")
        data = run_chicken_device.update_device_from_bytes(payload)
        _LOGGER.debug("Notification data: %s", data)
        coordinator.async_set_updated_data(data)

    await run_chicken_device.register_notification_callback(notification_callback)

    return True


# Reload entry when options are updated
async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Updated options %s", entry.options)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


# Remove entry and assure the device will be disconnected
async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    address = entry.unique_id
    if address is None:
        msg = "No address found for Run-Chicken device during removal."
        raise ValueError(msg)
    ble_device = async_ble_device_from_address(hass, address)
    client = await establish_connection(BleakClient, ble_device, ble_device.address)
    await client.disconnect()
