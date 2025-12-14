"""
BLE controller for the Run-Chicken coop door.

Exposes the `RunChickenCover` class which wraps a `BleakClient` and provides
high-level coroutines to open and close the door by writing command packets to
the device's write characteristic. Connections are made via
`bleak_retry_connector.establish_connection`, and command writes are retried on
transient Bluetooth errors using the `retry_bluetooth_connection_error`
decorator.

This module is part of the Home Assistant integration for Run-Chicken and is
safe to import (no side effects at import time).
"""

import logging

from bleak import BleakClient
from bleak_retry_connector import retry_bluetooth_connection_error

from .const import WRITE_CHAR_UUID
from .create_packet import create_close_packet, create_open_packet

_LOGGER = logging.getLogger(__name__)


class RunChickenController:
    """
    Controller for a Run-Chicken coop door over BLE.

    This helper wraps a `BleakClient` and exposes high-level coroutines to
    open and close the door by writing command packets to the device's
    write characteristic.
    """

    def __init__(self, client: BleakClient) -> None:
        """
        Initialize the controller.

        Args:
            client: An established `BleakClient` connected to the target device.

        """
        super().__init__()
        self.client = client

    @property
    def is_connected(self) -> bool:
        """
        Whether the underlying BLE client is currently connected.

        Returns:
            bool: True if connected, False otherwise.

        """
        return self.client.is_connected

    @retry_bluetooth_connection_error()
    async def open_cover(self) -> None:
        """
        Send the command to open the coop door.

        Writes an "open" command packet to the device's write characteristic.
        Retries on transient Bluetooth errors via the decorator.
        """
        packet = create_open_packet()
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)

    @retry_bluetooth_connection_error()
    async def close_cover(self) -> None:
        """
        Send the command to close the coop door.

        Writes a "close" command packet to the device's write characteristic.
        Retries on transient Bluetooth errors via the decorator.
        """
        packet = create_close_packet()
        await self.client.write_gatt_char(WRITE_CHAR_UUID, packet)
