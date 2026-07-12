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

from .protocol import READ_CHAR_UUID, WRITE_CHAR_UUID, RunChickenProtocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak import BleakClient, BLEDevice

    from .models import RunChickenDeviceData

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
        # Optional debug hook invoked as (direction, payload) for every raw
        # message exchanged with the door when set ("RX" received, "TX" sent).
        self.raw_recorder: Callable[[str, bytes | bytearray], None] | None = None

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

        # Re-subscribe notifications so push updates resume after a reconnect, and
        # so we catch any state the door pushes in reply to the hello below.
        await self._async_subscribe_notifications()

        # The official GIANT app sends a session-init "hello" right after
        # connecting; we do the same for every model, once per connection.
        await self._async_send_command(self.protocol.session_init_packet(), client=client)

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
        if self.raw_recorder is not None:
            self.raw_recorder("RX", payload)
        return self.protocol.parse_status(payload)

    # --- Door commands ---

    @retry_bluetooth_connection_error()
    async def async_open(self) -> None:
        """Open the Run-Chicken door."""
        await self._async_send_command(self.protocol.open_packet())

    @retry_bluetooth_connection_error()
    async def async_close(self) -> None:
        """Close the Run-Chicken door."""
        await self._async_send_command(self.protocol.close_packet())

    @retry_bluetooth_connection_error()
    async def async_write_settings(self, current: RunChickenDeviceData, **changes: object) -> None:
        """
        Change door settings (motor mode / schedule) with a read-modify-write.

        The door's settings command carries every setting in one frame, so the
        packet is built from ``current`` (the latest snapshot) with ``changes``
        applied on top - see ``RunChickenProtocol.settings_packet``. Raises
        ``ValueError`` if the merged settings are incomplete, and does not move
        the door.
        """
        packet = self.protocol.settings_packet(current, **changes)
        await self._async_send_command(packet)

    async def _async_send_command(self, packet: bytes, client: BleakClient | None = None) -> None:
        """
        Write a command frame to the door, recording it when recording is on.

        Connects (or reconnects) first, unless a freshly established ``client`` is
        supplied — as it is for the session-init "hello", which is sent from
        within the connection setup itself.
        """
        if client is None:
            client = await self.async_get_client()
        if self.raw_recorder is not None:
            self.raw_recorder("TX", packet)
        await client.write_gatt_char(WRITE_CHAR_UUID, packet)
