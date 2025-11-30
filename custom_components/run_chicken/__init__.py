"""
Custom integration to integrate Run-Chicken with Home Assistant.

For more details about this integration, please refer to
https://github.com/bkanuka/ha-run-chicken
"""

from __future__ import annotations
#
# import logging
# from datetime import timedelta
# from typing import TYPE_CHECKING
#
# from homeassistant.components.bluetooth import (
#     async_ble_device_from_address,
# )
# from bleak_retry_connector import establish_connection
# from homeassistant.config_entries import ConfigEntry
# from homeassistant.const import Platform
# from homeassistant.core import HomeAssistant
#
# from run_chicken.run_chicken_ble.const import DOMAIN, LOGGER
#
# _LOGGER = logging.getLogger(__name__)
#
# if TYPE_CHECKING:
#     from homeassistant.core import HomeAssistant
#
# PLATFORMS: list[Platform] = [
#     Platform.BINARY_SENSOR,
#     Platform.COVER,
# ]
#
# async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """Set up example BLE device from a config entry."""
#     hass.data.setdefault(DOMAIN, {})
#     address = entry.unique_id
#     assert address is not None
#
#     _LOGGER.debug("Thunderboard device address %s", address)
#     run_chicken = ThunderboardBluetoothDeviceData(_LOGGER)
#     scan_interval = DEFAULT_SCAN_INTERVAL
#
#     async def _async_update_method():
#         """ Get data from Thunderboard BLE. """
#         _LOGGER.debug("Thunderboard update method.")
#         ble_device = async_ble_device_from_address(hass, address)
#         if not ble_device:
#             raise ConfigEntryNotReady(
#                 f"Could not find Thunderboard device with address {address}"
#             )
#         _LOGGER.debug("Thunderboard BLE device is %s", ble_device)
#
#         try:
#             data = await thunderboard.update_device(ble_device)
#         except Exception as err:
#             raise UpdateFailed(f"Unable to fetch data: {err}") from err
#
#         return data
#
#     _LOGGER.debug("Polling interval is set to: %s seconds", scan_interval)
#
#     coordinator = hass.data.setdefault(DOMAIN, {})[
#         entry.entry_id
#     ] = DataUpdateCoordinator(
#         hass,
#         _LOGGER,
#         name=DOMAIN,
#         update_method=_async_update_method,
#         update_interval=timedelta(seconds=scan_interval),
#     )
#
#     await coordinator.async_config_entry_first_refresh()
#
#     await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
#
#     return True
#
#
# async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#     """ Unload a config entry. """
#     if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
#         hass.data[DOMAIN].pop(entry.entry_id)
#
#     return unload_ok
#
#
# async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
#     """ Handle removal of an entry. """
#     address = entry.unique_id
#     assert address is not None
#     ble_device = async_ble_device_from_address(hass, address)
#     client = await establish_connection(BleakClient, ble_device, ble_device.address)
#     await client.disconnect()