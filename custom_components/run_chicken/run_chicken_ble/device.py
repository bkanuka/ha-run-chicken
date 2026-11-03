"""BLE device interface for Run-Chicken devices."""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import deque
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

#: Number of recent idle battery readings to smooth over. Readings taken while
#: the motor runs (or right after a reconnect) occasionally sag; the voltage
#: itself drifts slowly, so the median of the last few readings filters
#: single outliers in both directions.
BATTERY_SMOOTHING_READINGS = 5

#: Without a persistent connection, how long to stay connected after a poll
#: (to catch the state the door pushes in reply to the session hello) and after
#: a door command (to catch the post-movement frame, incl. the under-load
#: battery reading, once the motor has finished).
RELEASE_AFTER_POLL_SECONDS = 5.0
RELEASE_AFTER_COMMAND_SECONDS = 60.0


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

        # Connection strategy: stay connected (push updates, more battery use) or
        # connect on demand and release shortly after each operation.
        self.persistent: bool = True
        self._release_handle: asyncio.TimerHandle | None = None
        self._release_deadline: float = 0.0
        # Set while we drop the link on purpose in on-demand mode, so the
        # disconnect callback doesn't trigger a reconnect.
        self._releasing = False

        # Recent idle battery readings, for smoothing.
        self._battery_readings: deque[int] = deque(maxlen=BATTERY_SMOOTHING_READINGS)
        self._battery_under_load: int | None = None

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
        # Any operation keeps the link up; a release is re-armed when it ends.
        self._cancel_release()

        if self._client is not None and self._client.is_connected:
            return self._client

        if self._expected_disconnect:
            msg = "Run-Chicken device is shutting down."
            raise UpdateFailed(msg)

        def on_disconnect(disconnected_client: BleakClient) -> None:
            self._client = None
            if self._expected_disconnect or self._releasing:
                _LOGGER.debug("Device %s disconnected as requested", disconnected_client.address)
                return
            _LOGGER.warning("Device %s disconnected unexpectedly", disconnected_client.address)
            # Notifications die with the connection; in persistent mode ask the
            # owner to reconnect. In on-demand mode the next poll reconnects.
            if self.persistent and self.disconnect_callback is not None:
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

        # The official apps send a session-init "hello" right after connecting;
        # we do the same for every model, once per connection. The GIANT needs
        # it before commands, and without it the T-50 only returns its stale
        # status frame from the previous session instead of a fresh one.
        await self._async_send_command(self.protocol.session_init_packet(), client=client)

        return client

    def schedule_release(self, delay: float) -> None:
        """
        In on-demand mode, disconnect ``delay`` seconds from now.

        A pending release is only ever pushed later, never earlier, so a quick
        poll during a command's grace period doesn't cut it short. No-op with a
        persistent connection.
        """
        if self.persistent:
            return
        loop = asyncio.get_running_loop()
        # Keep any later deadline already promised (e.g. a command's grace
        # period), even if its timer was paused by an operation in between.
        deadline = max(loop.time() + delay, self._release_deadline)
        self._cancel_release()
        self._release_deadline = deadline
        self._release_handle = loop.call_at(
            deadline, lambda: loop.create_task(self._async_release(), name="run_chicken_release")
        )

    def _cancel_release(self) -> None:
        if self._release_handle is not None:
            self._release_handle.cancel()
            self._release_handle = None

    async def _async_release(self) -> None:
        """Drop the on-demand connection to save the door's battery."""
        self._release_handle = None
        client = self._client
        if client is None or not client.is_connected:
            return
        _LOGGER.debug("Releasing on-demand connection to %s", client.address)
        self._releasing = True
        try:
            await client.disconnect()
        finally:
            self._client = None
            self._releasing = False

    async def async_disconnect(self) -> None:
        """Disconnect and suppress auto-reconnect; used during teardown."""
        self._cancel_release()
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
        self.schedule_release(RELEASE_AFTER_POLL_SECONDS)
        return self.data_from_bytes(payload)

    def data_from_bytes(self, payload: bytes | bytearray) -> RunChickenDeviceData:
        """Build a fresh state snapshot from a raw device payload."""
        _LOGGER.debug("Building state from bytes: %s", payload.hex())
        if self.raw_recorder is not None:
            self.raw_recorder("RX", payload)
        raw, under_load = self.protocol.parse_battery_raw(payload)
        if raw is not None:
            if under_load:
                self._battery_under_load = raw
            else:
                self._battery_readings.append(raw)
        battery_idle = round(statistics.median(self._battery_readings)) if self._battery_readings else None
        return RunChickenDeviceData(
            door_state=self.protocol.parse_door_state(payload),
            battery_raw=battery_idle,
            battery_raw_under_load=self._battery_under_load,
            schedule=self.protocol.parse_schedule(payload),
            raw_payload=bytes(payload),
        )

    # --- Door commands ---

    @retry_bluetooth_connection_error()
    async def async_open(self) -> None:
        """Open the Run-Chicken door."""
        await self._async_send_command(self.protocol.open_packet())
        self.schedule_release(RELEASE_AFTER_COMMAND_SECONDS)

    @retry_bluetooth_connection_error()
    async def async_close(self) -> None:
        """Close the Run-Chicken door."""
        await self._async_send_command(self.protocol.close_packet())
        self.schedule_release(RELEASE_AFTER_COMMAND_SECONDS)

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
