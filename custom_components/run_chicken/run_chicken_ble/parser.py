"""BLE parser for Run-Chicken devices."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bleak import BleakClient, BleakGATTCharacteristic, BLEDevice
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

# The read characteristic payload encodes the door state in a single byte at
# this offset (0 = open, 1 = closed).
DOOR_STATE_OFFSET = 17


class RunChickenDevice:
    """Representation of a Run-Chicken BLE device."""

    def __init__(
        self,
        ble_device: BLEDevice,
        client: BleakClient | None = None,
        device_data: RunChickenDeviceData | None = None,
    ) -> None:
        """Initialize the Run-Chicken device."""
        super().__init__()

        self.ble_device: BLEDevice = ble_device
        self._client: BleakClient | None = client

        if device_data is None:
            self._device_data: RunChickenDeviceData = RunChickenDeviceData(address=ble_device.address)
        else:
            self._device_data: RunChickenDeviceData = device_data

    @property
    def client(self) -> BleakClient | None:
        """Return the BLE client."""
        return self._client

    @property
    def address(self) -> str:
        """Return the BLE address of the device."""
        return self._device_data.address

    @property
    def device_data(self) -> RunChickenDeviceData:
        """Return the device data."""
        return self._device_data

    def _connected_read_char(self) -> tuple[BleakClient, BleakGATTCharacteristic]:
        """Return the connected client and its read characteristic, or raise."""
        if self._client is None:
            msg = "Run-Chicken device is not connected."
            raise UpdateFailed(msg)
        char = self._client.services.get_characteristic(READ_CHAR_UUID)
        if char is None:
            msg = f"Read characteristic {READ_CHAR_UUID} not found on device."
            raise UpdateFailed(msg)
        return self._client, char

    async def register_notification_callback(self, callback: Callable) -> None:
        """Register a callback to be called when the device sends a notification."""
        client, read_char = self._connected_read_char()
        await client.start_notify(read_char, callback)

    async def ensure_client_connected(self) -> None:
        """Ensure the client is connected."""
        if self._client is None or not self._client.is_connected:
            await self._get_client()

    async def _get_client(self) -> BleakClient:
        """Get the client from the ble device."""

        def on_disconnect(client: BleakClient) -> None:
            _LOGGER.warning("Device %s disconnected unexpectedly", client.address)
            self._client = None

        if self.ble_device.address != self._device_data.address:
            self._client = None

        if isinstance(self._client, BleakClient) and self._client.is_connected:
            return self._client

        _LOGGER.debug("Getting BleakClient for Run-Chicken door: %s", self.ble_device.address)
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            self.ble_device,
            self.ble_device.address,
            disconnected_callback=on_disconnect,
        )
        if self._client is None:
            msg = "Failed to establish connection to device."
            raise UpdateFailed(msg)

        self._device_data.address = self._client.address

        return self._client

    @staticmethod
    def _parse_door_state(payload: bytes | bytearray) -> RunChickenDoorState:
        """Parse the door state out of a device payload."""
        _LOGGER.debug("Parsing payload: %s", payload.hex())
        if len(payload) <= DOOR_STATE_OFFSET:
            _LOGGER.warning("Payload too short to contain door state: %s", payload.hex())
            return RunChickenDoorState.UNKNOWN
        return RunChickenDoorState.from_raw(payload[DOOR_STATE_OFFSET])

    @retry_bluetooth_connection_error()
    async def _read_payload(self) -> bytearray:
        """Read the raw payload from the device's read characteristic."""
        client, char = self._connected_read_char()
        return await client.read_gatt_char(char)

    def update_device_from_bytes(self, payload: bytes | bytearray) -> RunChickenDeviceData:
        """Update the device from a bytes payload."""
        _LOGGER.debug("Updating device from bytes: %s", payload.hex())
        self._device_data.door_state = self._parse_door_state(payload)
        return self._device_data

    async def update_device(self) -> RunChickenDeviceData:
        """Connect to the device with BLE and retrieve data."""
        await self.ensure_client_connected()
        self._device_data.door_state = self._parse_door_state(await self._read_payload())
        return self._device_data
