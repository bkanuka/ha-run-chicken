from __future__ import annotations

import asyncio
import logging
import struct

from bleak import BLEDevice, BleakClient, BleakScanner
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    retry_bluetooth_connection_error,
)

from run_chicken.run_chicken_ble.const import READ_CHAR_UUID
from run_chicken.run_chicken_ble.models import RunChickenDevice, RunChickenDoorState

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


class RunChickenDeviceData:

    def __init__(self, client: BleakClient | None = None, device: RunChickenDevice = None):
        super().__init__()
        self._client: BleakClient | None = client

        if device is None:
            self._device: RunChickenDevice = RunChickenDevice()
        else:
            self._device: RunChickenDevice = device

    async def _get_client(self, ble_device: BLEDevice) -> BleakClient:
        """Get the client from the ble device."""
        if self._client is not None:
            return self._client

        _LOGGER.debug("Getting BleakClient for Run-Chicken door: %s", ble_device.address)
        self._client = await establish_connection(
            BleakClientWithServiceCache, ble_device, ble_device.address
        )
        self._device.address = self._client.address
        self._device.name = self._client.name
        return self._client

    @retry_bluetooth_connection_error()
    async def _read_value_chars(self) -> dict[str, int | float]:
        """ Get the payload value from the characteristic, processed. """
        char = self._client.services.get_characteristic(READ_CHAR_UUID)
        payload = await self._client.read_gatt_char(char)

        _LOGGER.debug(": %s", payload)

        char_values = {}
        for key, config in READ_VALUES.items():
            format_str = config["format"]
            value = struct.unpack(format_str, payload[:18])[0]
            if "parser" in config:
                value = config["parser"](value)
            char_values[key] = value

        return char_values

    async def update_device(self, ble_device: BLEDevice) -> RunChickenDevice:
        """ Connects to the device with BLE and retrieves data """
        self._client = await self._get_client(ble_device)

        try:
            char_values = await self._read_value_chars()
        finally:
            await self._client.disconnect()

        _LOGGER.debug("Updating device with values: %s", char_values)

        for k, v in char_values.items():
            if hasattr(self._device, k):
                setattr(self._device, k, v)
            else:
                self._device.values[k] = v

        return self._device


async def test_update_device(test_addr: str):
    ble_device = await BleakScanner.find_device_by_address(test_addr, timeout=10.0)

    if not ble_device:
        print(f"Device with address {test_addr} not found.")
        return

    parser = RunChickenDeviceData()
    device: RunChickenDevice = await parser.update_device(ble_device)

    print(device)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_addr = "00:80:e1:22:43:0d"
    asyncio.run(test_update_device(test_addr))
