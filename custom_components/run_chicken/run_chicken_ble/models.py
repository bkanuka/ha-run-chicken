"""Models for RunChicken BLE integration."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime as dt


class RunChickenDoorState(Enum):
    """Possible states of the RunChicken door."""

    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2


@dataclasses.dataclass(frozen=True)
class RunChickenDeviceData:
    """
    Immutable snapshot of a Run-Chicken door's observed state.

    This is the coordinator's data payload, rebuilt on every update and pushed to
    entities. It holds only values that change over the device's life; static
    identity (model, manufacturer, address) lives on ``RunChickenDevice``.
    """

    door_state: RunChickenDoorState = RunChickenDoorState.UNKNOWN
    #: Smoothed idle battery byte (payload[13]); see ``RunChickenDevice``.
    battery_raw: int | None = None
    #: Battery byte from the last post-movement (0xB5) frame, i.e. under load.
    battery_raw_under_load: int | None = None
    #: Door schedule, if the payload carries it (``None`` otherwise).
    schedule: RunChickenSchedule | None = None
    #: The full payload the snapshot was built from, kept for diagnostics.
    raw_payload: bytes = b""


@dataclasses.dataclass(frozen=True)
class RunChickenSchedule:
    """
    Schedule and location settings echoed by the door in its status payload.

    Decoded from a T-50 with newer firmware (long payload). Times are the
    door's own computed open/close times for the current day, in UTC; offsets
    are the delays configured in the app, in minutes. Modes are raw values:
    1 has been observed for "sunrise/sunset" mode; the meaning of others
    (e.g. 2) is not confirmed yet.
    """

    latitude: int | None
    longitude: int | None
    open_mode: int
    close_mode: int
    open_time: dt.datetime | None
    close_time: dt.datetime | None
    open_offset: int
    close_offset: int
    #: Anti-pinch (obstacle detection) enabled, from payload[41]; ``None`` if
    #: the payload is too short to carry it.
    anti_pinch: bool | None = None
