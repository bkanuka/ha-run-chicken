"""Models for RunChicken BLE integration."""

from __future__ import annotations

import dataclasses
import datetime as dt
from enum import Enum


class RunChickenDoorState(Enum):
    """Possible states of the RunChicken door."""

    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2


class RunChickenScheduleMode(Enum):
    """
    Open/close schedule mode, as selected in the app.

    Reverse-engineered by diffing raw status payloads against known app
    settings changes (not from any official protocol documentation). ``2`` is
    not a value the app produces and is treated as UNKNOWN like anything else
    unrecognised.
    """

    UNKNOWN = -1
    MANUAL = 0
    SUNRISE_SUNSET = 1
    TIMER = 3


class RunChickenMotorMode(Enum):
    """
    Anti-pinch / power-mode selector, as set in the app.

    These two app toggles are mutually exclusive (enabling one disables the
    other), so the door reports a single selector rather than independent
    flags. Reverse-engineered the same way as ``RunChickenScheduleMode``.
    """

    UNKNOWN = -1
    OFF = 0
    ANTI_PINCH = 1
    POWER_MODE = 2


@dataclasses.dataclass(frozen=True)
class RunChickenDeviceData:
    """
    Immutable snapshot of a Run-Chicken door's observed state.

    This is the coordinator's data payload, rebuilt on every update and pushed to
    entities. It holds only values that change over the device's life; static
    identity (model, manufacturer, address) lives on ``RunChickenDevice``.
    """

    door_state: RunChickenDoorState = RunChickenDoorState.UNKNOWN
    firmware_version: str | None = None
    #: Battery voltage in volts. Sags under motor load (draws down while the
    #: door is opening/closing) and recovers afterward, so a momentary dip
    #: during a transition is expected, not a fault.
    battery_voltage: float | None = None
    motor_mode: RunChickenMotorMode = RunChickenMotorMode.UNKNOWN
    open_schedule_mode: RunChickenScheduleMode = RunChickenScheduleMode.UNKNOWN
    close_schedule_mode: RunChickenScheduleMode = RunChickenScheduleMode.UNKNOWN
    open_offset_minutes: int | None = None
    close_offset_minutes: int | None = None
    #: Resolved open time (UTC), populated regardless of which schedule mode
    #: computed it (Timer sets it directly; Sunrise/Sunset resolves it daily).
    open_time: dt.time | None = None
    #: Resolved close time (UTC) - same shape as open_time, by symmetry with
    #: the open/close schedule-mode and offset-minutes pairs. UNVERIFIED:
    #: the byte offset behind this is hypothesized, not independently
    #: confirmed against a real Close->Time app setting.
    close_time: dt.time | None = None
