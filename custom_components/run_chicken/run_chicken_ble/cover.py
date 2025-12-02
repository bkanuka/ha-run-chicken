import logging

from bleak import BleakClient, BLEDevice
from bleak_retry_connector import establish_connection, retry_bluetooth_connection_error

from .const import WRITE_CHAR_UUID
from .create_packet import create_packet

_LOGGER = logging.getLogger(__name__)


class RunChickenCover:
    def __init__(self, client: BleakClient) -> None:
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
    async def open_cover(self) -> None:
        packet = create_packet(open_door=True, close_door=False)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)

    @retry_bluetooth_connection_error()
    async def close_cover(self) -> None:
        packet = create_packet(open_door=False, close_door=True)
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
