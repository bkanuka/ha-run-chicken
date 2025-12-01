"""
Custom integration to integrate Run-Chicken with Home Assistant.

For more details about this integration, please refer to
https://github.com/bkanuka/ha-run-chicken
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakGATTCharacteristic, BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth import (
    async_ble_device_from_address, async_register_callback, BluetoothCallbackMatcher,
)
from homeassistant.components.bluetooth.models import BluetoothServiceInfoBleak, BluetoothChange
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed, DataUpdateCoordinator

from .run_chicken_ble.parser import RunChickenDevice
from .const import DEFAULT_SCAN_INTERVAL, EVENT_DEBOUNCE_TIME, DOMAIN
from .run_chicken_ble.models import RunChickenDeviceData

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.COVER,
]

last_event_time = time.time()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BLE device from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    address = entry.unique_id
    assert address is not None
    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.debug("Run-Chicken device address %s", address)
    run_chicken = RunChickenDevice()
    scan_interval = DEFAULT_SCAN_INTERVAL

    async def _async_update_method():
        """ Get data from Run-Chicken BLE. """
        _LOGGER.debug("Running Run-Chicken update method.")
        _LOGGER.debug(f"Trying to get ble_device with address {address}")

        ble_device = async_ble_device_from_address(hass, address, connectable=True)
        if not ble_device:
            raise UpdateFailed(
                f"Could not find Run-Chicken device with address {address}"
            )
        _LOGGER.debug("Run-Chicken BLE device is %s", ble_device)

        try:
            data: RunChickenDeviceData = await run_chicken.update_device(ble_device)
        except Exception as err:
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

        return data


    _LOGGER.debug("Polling interval is set to: %s seconds", scan_interval)

    # Create Coordinator
    coordinator = hass.data.setdefault(DOMAIN, {})[
        entry.entry_id
    ] = DataUpdateCoordinator(
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
        loop.create_task(coordinator.async_request_refresh())


    async_register_callback(
        hass,
        async_handle_bluetooth_event,
        BluetoothCallbackMatcher(address=address),
        BluetoothScanningMode.ACTIVE,
    )

    def notification_callback(gatt_char: BleakGATTCharacteristic, payload: bytearray):
        """Handle notification data from the device."""
        _LOGGER.debug(f"Handling notification payload")
        data = run_chicken.update_device_from_bytes(payload)
        _LOGGER.debug(f"Notification data: {data}")
        coordinator.async_set_updated_data(data)

    await run_chicken.register_notification_callback(notification_callback)

    return True


# Reload entry when options are updated
async def update_listener(hass: HomeAssistant, entry: ConfigEntry)-> None:
    """Handle options update."""
    _LOGGER.debug("Updated options %s", entry.options)
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """ Unload a config entry. """
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

# Remove entry and assure the device will be disconnected
async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """ Handle removal of an entry. """
    address = entry.unique_id
    assert address is not None
    ble_device = async_ble_device_from_address(hass, address)
    client = await establish_connection(BleakClient, ble_device, ble_device.address)
    await client.disconnect()