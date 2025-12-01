from __future__ import annotations

import asyncio
import logging
import struct
from typing import Callable, Awaitable

from bleak import BLEDevice, BleakClient, BleakScanner, BleakGATTCharacteristic
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    retry_bluetooth_connection_error,
)

from run_chicken.run_chicken_ble.const import READ_CHAR_UUID
from run_chicken.run_chicken_ble.models import RunChickenDeviceData, RunChickenDoorState

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

    def __init__(self, client: BleakClient | None = None, device: RunChickenDeviceData = None):
        super().__init__()
        self._client: BleakClient | None = client

        if device is None:
            self._device: RunChickenDeviceData = RunChickenDeviceData()
        else:
            self._device: RunChickenDeviceData = device

    async def register_notification_callback(self, callback: Callable):
        read_char = self._client.services.get_characteristic(READ_CHAR_UUID)
        await self._client.start_notify(read_char, callback)

    async def _get_client(self, ble_device: BLEDevice) -> BleakClient:
        """Get the client from the ble device."""

        def on_disconnect(client):
            _LOGGER.warning(f"Device {self._device.address} disconnected unexpectedly")
            self._client = None

        if isinstance(self._client, BleakClient) and self._client.is_connected:
            return self._client

        _LOGGER.debug("Getting BleakClient for Run-Chicken door: %s", ble_device.address)
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            ble_device.address,
            disconnected_callback=on_disconnect,
        )
        self._device.address = self._client.address

        return self._client

    @staticmethod
    def _parse_payload(payload: bytearray) -> dict[str, int | float]:
        _LOGGER.debug("Parsing payload: %s", payload)

        values = {}
        for key, config in READ_VALUES.items():
            value = struct.unpack(config["format"], payload[:18])[0]
            if "parser" in config:
                value = config["parser"](value)
            values[key] = value

        return values

    def _update_device_from_values(self, values: dict[str, int | float]):
        _LOGGER.debug("Updating device with values: %s", values)

        for k, v in values.items():
            if hasattr(self._device, k):
                setattr(self._device, k, v)
            else:
                self._device.values[k] = v

    @retry_bluetooth_connection_error()
    async def _poll_values(self) -> dict[str, int | float]:
        """ Poll device for new values """
        char = self._client.services.get_characteristic(READ_CHAR_UUID)
        payload: bytearray = await self._client.read_gatt_char(char)

        return self._parse_payload(payload)


    def update_device_from_bytes(self, payload: bytes | bytearray) -> RunChickenDeviceData:
        """ Update the device from a bytes payload. """
        _LOGGER.debug("Updating device with payload: %s", payload)

        values = self._parse_payload(payload)
        self._update_device_from_values(values)
        return self._device


    async def update_device(self, ble_device: BLEDevice) -> RunChickenDeviceData:
        """ Connects to the device with BLE and retrieves data """
        _LOGGER.debug(f"Polling device {ble_device.address}")
        self._client = await self._get_client(ble_device)
        values = await self._poll_values()
        self._update_device_from_values(values)
        return self._device


async def test_update_device(test_addr: str):
    ble_device = await BleakScanner.find_device_by_address(test_addr, timeout=10.0)

    if not ble_device:
        print(f"Device with address {test_addr} not found.")
        return

    parser = RunChickenDevice()
    device: RunChickenDeviceData = await parser.update_device(ble_device)

    print(device)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_addr = "00:80:e1:22:43:0d"
    asyncio.run(test_update_device(test_addr))
