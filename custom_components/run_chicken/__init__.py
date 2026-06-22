"""
Custom integration to integrate Run-Chicken with Home Assistant.

For more details about this integration, please refer to
https://github.com/bkanuka/ha-run-chicken
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import RunChickenCoordinator
from .run_chicken_ble.device import RunChickenDevice

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.COVER,
]

type RunChickenConfigEntry = ConfigEntry[RunChickenCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RunChickenConfigEntry) -> bool:
    """Set up a Run-Chicken door from a config entry."""
    address = entry.unique_id
    if address is None:
        msg = "No address found for Run-Chicken device."
        raise ConfigEntryNotReady(msg)

    ble_device = async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        msg = f"BLE device with address {address} not found."
        raise ConfigEntryNotReady(msg)

    _LOGGER.debug("Setting up Run-Chicken device %s", address)
    door_coordinator = RunChickenCoordinator(hass, entry, RunChickenDevice(ble_device))
    await door_coordinator.async_init()
    entry.runtime_data = door_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RunChickenConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop auto-reconnect and drop the connection before tearing down.
    await entry.runtime_data.device.async_disconnect()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


# Remove entry and ensure the device will be disconnected
async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    address = entry.unique_id
    if address is None:
        msg = "No address found for Run-Chicken device during removal."
        raise ValueError(msg)
    ble_device = async_ble_device_from_address(hass, address)
    if ble_device is None:
        _LOGGER.debug("Run-Chicken device %s not available; nothing to disconnect", address)
        return
    client = await establish_connection(BleakClient, ble_device, ble_device.address)
    await client.disconnect()
