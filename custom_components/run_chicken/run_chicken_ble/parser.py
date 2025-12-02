"""BLE parser for Run-Chicken devices."""

from __future__ import annotations

import logging
import struct
from typing import TYPE_CHECKING

from bleak import BleakClient, BLEDevice
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    retry_bluetooth_connection_error,
)
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import READ_CHAR_UUID
from .models import RunChickenDeviceData, RunChickenDoorState

if TYPE_CHECKING:
    from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

DOOR_STATUS_PARSER = {
    0: RunChickenDoorState.OPEN,
    1: RunChickenDoorState.CLOSED
}

READ_VALUES = {
    "door_state": {
        "format": "17xB",  # Skip 17 bytes and read 1 byte as unsigned char
        "parser": lambda x: DOOR_STATUS_PARSER[x]
    }
}


class RunChickenDevice:
    """Representation of a Run-Chicken BLE device."""

    def __init__(self,
                 client: BleakClient | None = None,
                 device: RunChickenDeviceData = None) -> None:
        """Initialize the Run-Chicken device."""
        super().__init__()
        self._client: BleakClient | None = client

        if device is None:
            self._device: RunChickenDeviceData = RunChickenDeviceData()
        else:
            self._device: RunChickenDeviceData = device

    @property
    def address(self) -> str:
        """Return the BLE address of the device."""
        return self._client.address

    async def register_notification_callback(self, callback: Callable) -> None:
        """Register a callback to be called when the device sends a notification."""
        read_char = self._client.services.get_characteristic(READ_CHAR_UUID)
        await self._client.start_notify(read_char, callback)

    async def _get_client(self, ble_device: BLEDevice) -> BleakClient:
        """Get the client from the ble device."""

        def on_disconnect(client: BleakClient) -> None:
            _LOGGER.warning("Device %s disconnected unexpectedly", client.address)
            self._client = None

        if ble_device.address != self._device.address:
            self._client = None

        if isinstance(self._client, BleakClient) and self._client.is_connected:
            return self._client

        _LOGGER.debug(
            "Getting BleakClient for Run-Chicken door: %s",
            ble_device.address
        )
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.address,
            disconnected_callback=on_disconnect,
        )
        if self._client is None:
            msg = "Failed to establish connection to device."
            raise UpdateFailed(msg)
        self._device.address = self._client.address

        return self._client

    @staticmethod
    def _parse_payload(payload: bytearray) -> dict[str, int | float]:
        _LOGGER.debug("Parsing payload: %s", payload.hex())

        values = {}
        for key, config in READ_VALUES.items():
            value = struct.unpack(config["format"], payload[:18])[0]
            if "parser" in config:
                value = config["parser"](value)
            values[key] = value

        return values

    def _update_device_from_values(self, values: dict[str, int | float]) -> None:
        _LOGGER.debug("Updating device with values: %s", values)

        for k, v in values.items():
            if hasattr(self._device, k):
                setattr(self._device, k, v)
            else:
                self._device.values[k] = v

    @retry_bluetooth_connection_error()
    async def _poll_values(self) -> dict[str, int | float]:
        """Poll device for new values."""
        char = self._client.services.get_characteristic(READ_CHAR_UUID)
        payload: bytearray = await self._client.read_gatt_char(char)

        return self._parse_payload(payload)

    def update_device_from_bytes(self,
                                 payload: bytes | bytearray
                                 ) -> RunChickenDeviceData:
        """Update the device from a bytes payload."""
        _LOGGER.debug("Updating device from bytes: %s", payload.hex())

        values = self._parse_payload(payload)
        self._update_device_from_values(values)
        return self._device

    async def update_device(self,
                            ble_device: BLEDevice | None = None
                            ) -> RunChickenDeviceData:
        """Connect to the device with BLE and retrieve data."""
        if ble_device is None:
            if self._client is None:
                msg = "No BLE device provided and no existing client."
                raise UpdateFailed(msg)
            _LOGGER.debug("Using existing client to update device.")
        else:
            _LOGGER.debug("Updating device with new BLE device: %s", ble_device)
            self._client = await self._get_client(ble_device)

        values = await self._poll_values()
        self._update_device_from_values(values)
        return self._device
