"""BLE device interface for Run-Chicken devices."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    retry_bluetooth_connection_error,
)
from homeassistant.helpers.update_coordinator import UpdateFailed

from .models import RunChickenDeviceData
from .protocol import READ_CHAR_UUID, WRITE_CHAR_UUID, RunChickenProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak import BleakClient, BLEDevice

_LOGGER = logging.getLogger(__name__)


class RunChickenDevice:
    """Representation of a Run-Chicken BLE device."""

    #: Device manufacturer, surfaced in the device registry.
    manufacturer = "Run-Chicken"

    def __init__(
        self,
        ble_device: BLEDevice,
        client: BleakClient | None = None,
    ) -> None:
        """Initialize the Run-Chicken device."""
        super().__init__()

        # Refreshed in place from new advertisements (see coordinator); the
        # address is stable but the object's adapter/path details go stale.
        self.ble_device: BLEDevice = ble_device
        self._client: BleakClient | None = client
        # Stored so notifications can be re-subscribed on every reconnect.
        self._notification_callback: Callable | None = None
        # Invoked on an unexpected disconnect so the owner can reconnect (which
        # re-subscribes notifications). Read at disconnect time, so it is safe to
        # assign any time before the connection drops.
        self.disconnect_callback: Callable[[], None] | None = None
        # Set during teardown so we don't fight an intentional disconnect.
        self._expected_disconnect = False
        # Tracks whether the once-per-connection session-init "hello" has been
        # sent; reset to False whenever a new connection is made.
        self._session_initialized = False

        # Pick the command-frame protocol from the advertised name (T-50 vs GIANT).
        self.protocol = RunChickenProtocol.for_advertised_name(ble_device.name)

    # --- Device identity ---

    @property
    def address(self) -> str:
        """Return the BLE address of the device."""
        return self.ble_device.address

    @property
    def name(self) -> str | None:
        """Return the door's advertised BLE name, if any."""
        return self.ble_device.name

    @property
    def model(self) -> str:
        """Return the door model, derived from the command-frame protocol."""
        return self.protocol.model

    # --- Connection management ---

    async def async_get_client(self) -> BleakClient:
        """
        Return a live client, connecting or reconnecting on demand.

        Reuses the current connection while it is healthy. Raises ``UpdateFailed``
        if the device is shutting down or a connection cannot be established.
        """
        if self._client is not None and self._client.is_connected:
            return self._client

        if self._expected_disconnect:
            msg = "Run-Chicken device is shutting down."
            raise UpdateFailed(msg)

        def on_disconnect(disconnected_client: BleakClient) -> None:
            _LOGGER.warning("Device %s disconnected unexpectedly", disconnected_client.address)
            self._client = None
            # Notifications die with the connection; ask the owner to reconnect.
            if not self._expected_disconnect and self.disconnect_callback is not None:
                self.disconnect_callback()

        _LOGGER.debug("Getting BleakClient for Run-Chicken door: %s", self.ble_device.address)
        client = await establish_connection(
            BleakClientWithServiceCache,
            self.ble_device,
            self.ble_device.address,
            disconnected_callback=on_disconnect,
            # Re-fetch the freshest BLEDevice on each retry so a stale path
            # captured at setup doesn't doom the connection.
            ble_device_callback=lambda: self.ble_device,
        )
        self._client = client

        # Fresh connection: the session-init must be re-sent before the next command.
        self._session_initialized = False

        # Re-subscribe notifications so push updates resume after a reconnect.
        await self._async_subscribe_notifications()

        return client

    async def async_disconnect(self) -> None:
        """Disconnect and suppress auto-reconnect; used during teardown."""
        self._expected_disconnect = True
        client = self._client
        self._client = None
        if client is not None and client.is_connected:
            await client.disconnect()

    # --- Push notifications ---

    async def register_notification_callback(self, callback: Callable) -> None:
        """
        Register a callback for device notifications.

        Notifications are only delivered over a live connection, so the callback
        is stored and automatically re-subscribed whenever the device reconnects.
        """
        self._notification_callback = callback
        await self._async_subscribe_notifications()

    async def _async_subscribe_notifications(self) -> None:
        """Subscribe the stored notification callback on the current client, if any."""
        if self._notification_callback is None or self._client is None:
            return
        read_char = self._client.services.get_characteristic(READ_CHAR_UUID)
        if read_char is None:
            _LOGGER.warning("Read characteristic %s not found; cannot subscribe to notifications", READ_CHAR_UUID)
            return
        await self._client.start_notify(read_char, self._notification_callback)
        _LOGGER.debug("Subscribed to Run-Chicken notifications on %s", self._client.address)

    # --- Reading state ---

    @retry_bluetooth_connection_error()
    async def poll_device(self) -> RunChickenDeviceData:
        """Connect to the device, read its raw state payload, and return a fresh snapshot."""
        client = await self.async_get_client()
        char = client.services.get_characteristic(READ_CHAR_UUID)
        if char is None:
            msg = f"Read characteristic {READ_CHAR_UUID} not found on device."
            raise UpdateFailed(msg)
        payload = await client.read_gatt_char(char)
        return self.data_from_bytes(payload)

    def data_from_bytes(self, payload: bytes | bytearray) -> RunChickenDeviceData:
        """Build a fresh state snapshot from a raw device payload."""
        _LOGGER.debug("Building state from bytes: %s", payload.hex())
        return RunChickenDeviceData(door_state=self.protocol.parse_door_state(payload))

    # --- Door commands ---

    @retry_bluetooth_connection_error()
    async def async_open(self) -> None:
        """Open the Run-Chicken door."""
        await self._async_send_command(self.protocol.open_packet())

    @retry_bluetooth_connection_error()
    async def async_close(self) -> None:
        """Close the Run-Chicken door."""
        await self._async_send_command(self.protocol.close_packet())

    async def _async_send_command(self, packet: bytes) -> None:
        """Connect if needed and write a command packet to the door."""
        client = await self.async_get_client()
        await self._async_session_init(client)
        await client.write_gatt_char(WRITE_CHAR_UUID, packet)

    async def _async_session_init(self, client: BleakClient) -> None:
        """
        Send the session-init "hello" once per connection, before any command.

        The official GIANT app sends this right after connecting; we do the same
        for every model. Sent once and reset on each reconnect.
        """
        if self._session_initialized:
            return
        await client.write_gatt_char(WRITE_CHAR_UUID, self.protocol.session_init_packet())
        self._session_initialized = True
        _LOGGER.debug("Sent %s session-init packet to %s", self.protocol.model, client.address)
