import asyncio
import logging

from bleak import BleakClient, BLEDevice
from bleak_retry_connector import establish_connection, retry_bluetooth_connection_error

from run_chicken.run_chicken_ble.const import WRITE_CHAR_UUID
from run_chicken.run_chicken_ble.create_packet import create_packet

_LOGGER = logging.getLogger(__name__)


class RunChickenCover:
    def __init__(
            self,
            client: BleakClient,
    ):
        super().__init__()
        self.client = client

    @classmethod
    async def from_ble_device(cls, ble_device: BLEDevice):
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        return cls(client)

    @property
    def is_connected(self):
        return self.client.is_connected

    @retry_bluetooth_connection_error()
    async def open_cover(self):
        packet = create_packet(open_door=True, close_door=False)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)

    @retry_bluetooth_connection_error()
    async def close_cover(self):
        packet = create_packet(open_door=False, close_door=True)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)