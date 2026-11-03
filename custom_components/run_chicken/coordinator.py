"""Data update coordinator for the Run-Chicken integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_register_callback,
)
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PERSISTENT_CONNECTION,
    CONF_POLL_INTERVAL,
    CONF_POLL_ON_SCHEDULE,
    DEFAULT_PERSISTENT_CONNECTION,
    DEFAULT_POLL_INTERVAL_MINUTES,
    DEFAULT_POLL_ON_SCHEDULE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .run_chicken_ble.models import RunChickenDeviceData

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak import BleakGATTCharacteristic
    from homeassistant.components.bluetooth import (
        BluetoothChange,
        BluetoothServiceInfoBleak,
    )
    from homeassistant.core import HomeAssistant

    from . import RunChickenConfigEntry
    from .run_chicken_ble.device import RunChickenDevice

_LOGGER = logging.getLogger(__name__)

#: Schedule-based polling: how long after a scheduled open/close to connect (the
#: motor needs ~15 s; a margin covers clock skew and the door's own delay).
POLL_AFTER_EVENT = timedelta(minutes=3)
#: Retry delay after a failed or inconclusive poll.
POLL_RETRY = timedelta(minutes=15)
#: Upper bound between polls, e.g. in manual mode where no times are known.
POLL_FALLBACK = timedelta(hours=24)


class RunChickenCoordinator(DataUpdateCoordinator[RunChickenDeviceData]):
    """Coordinate updates for a Run-Chicken door and own its BLE event wiring."""

    config_entry: RunChickenConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RunChickenConfigEntry, device: RunChickenDevice) -> None:
        """Initialize the coordinator for a single Run-Chicken device."""
        persistent = entry.options.get(CONF_PERSISTENT_CONNECTION, DEFAULT_PERSISTENT_CONNECTION)
        self.poll_on_schedule = not persistent and entry.options.get(CONF_POLL_ON_SCHEDULE, DEFAULT_POLL_ON_SCHEDULE)
        interval: timedelta | None
        if persistent:
            interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
        elif self.poll_on_schedule:
            interval = None  # polls are timed from the door's schedule instead
        else:
            interval = timedelta(minutes=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MINUTES))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=interval,
        )
        self.device = device
        self.device.persistent = persistent
        self._unsub_poll: Callable[[], None] | None = None
        self._next_poll: datetime | None = None

    async def async_init(self) -> None:
        """Connect, subscribe to notifications, and wire up reconnect handling."""
        # Reconnect on an unexpected disconnect; the closure reads the callback
        # at disconnect time, so setting it before the first refresh is fine.
        self.device.disconnect_callback = self._schedule_reconnect

        await self.async_config_entry_first_refresh()

        await self.device.register_notification_callback(self._handle_notification)

        if self.poll_on_schedule:
            self.config_entry.async_on_unload(self.async_add_listener(self._schedule_next_poll))
            self.config_entry.async_on_unload(self._cancel_poll)
            self._schedule_next_poll()

        # Refresh when the door advertises again (e.g. after dropping the link).
        self.config_entry.async_on_unload(
            async_register_callback(
                self.hass,
                self._handle_bluetooth_event,
                BluetoothCallbackMatcher(address=self.device.address),
                BluetoothScanningMode.ACTIVE,
            )
        )

    async def _async_update_data(self) -> RunChickenDeviceData:
        """Fetch the latest door state over BLE (also reconnects if needed)."""
        _LOGGER.debug("Polling Run-Chicken device %s", self.device.address)
        return await self.device.poll_device()

    # --- Schedule-based polling ---

    def _next_poll_time(self) -> datetime:
        """Pick when to connect next: just after the next scheduled operation."""
        now = dt_util.utcnow()
        if not self.last_update_success or self.data is None:
            return now + POLL_RETRY
        schedule = self.data.schedule
        if schedule is None or (schedule.open_time is None and schedule.close_time is None):
            # Manual mode or no schedule reported: nothing happens on its own.
            return now + POLL_FALLBACK
        candidates = [t + POLL_AFTER_EVENT for t in (schedule.open_time, schedule.close_time) if t is not None]
        upcoming = [t for t in candidates if t > now]
        if not upcoming:
            # Stale times (e.g. the door has not recomputed yet): look again soon.
            return now + POLL_RETRY
        return min(*upcoming, now + POLL_FALLBACK)

    @callback
    def _schedule_next_poll(self) -> None:
        """(Re)arm the single pending poll timer from the latest data."""
        target = self._next_poll_time()
        if self._unsub_poll is not None and target == self._next_poll:
            return
        self._cancel_poll()
        self._next_poll = target
        _LOGGER.debug("Next scheduled Run-Chicken poll at %s", target.isoformat())
        self._unsub_poll = async_track_point_in_utc_time(self.hass, self._async_scheduled_poll, target)

    @callback
    def _cancel_poll(self) -> None:
        if self._unsub_poll is not None:
            self._unsub_poll()
            self._unsub_poll = None

    async def _async_scheduled_poll(self, _now: datetime) -> None:
        """Timer callback: poll the door, then re-arm for the next operation."""
        self._unsub_poll = None
        self._next_poll = None
        await self.async_refresh()
        # Listeners re-arm on success; make sure a timer exists on failure too.
        if self._unsub_poll is None:
            self._schedule_next_poll()

    def _handle_notification(self, _gatt_char: BleakGATTCharacteristic, payload: bytearray) -> None:
        """Push a device notification payload into the coordinator."""
        _LOGGER.debug("Handling notification payload")
        self.async_set_updated_data(self.device.data_from_bytes(payload))

    # BluetoothChange is a functional Enum (Enum("BluetoothChange", ...)) that
    # PyCharm can't use as a type annotation, though the hint is correct for ty.
    # noinspection PyTypeHints
    def _handle_bluetooth_event(self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange) -> None:
        """Refresh on a Bluetooth advertisement (reconnects and re-subscribes)."""
        _LOGGER.debug("BLE event received: %s, change %s", service_info, change)
        # Keep the device's BLEDevice fresh so reconnects use the best path.
        self.device.ble_device = service_info.device
        # The door only advertises while nobody is connected. With a persistent
        # connection an advertisement means the link dropped, so reconnect. In
        # on-demand mode the door advertises all the time between polls, and
        # reconnecting on every advertisement would defeat the purpose.
        if not self.device.persistent:
            return
        self.hass.async_create_task(self.async_request_refresh(), f"{DOMAIN}_advertisement_refresh")

    def _schedule_reconnect(self) -> None:
        """Reconnect after an unexpected disconnect so push updates resume."""
        _LOGGER.debug("Run-Chicken %s disconnected; scheduling reconnect", self.device.address)
        self.hass.async_create_task(self.async_request_refresh(), f"{DOMAIN}_reconnect")
