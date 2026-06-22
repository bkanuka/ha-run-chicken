"""Models for RunChicken BLE integration."""

from __future__ import annotations

import dataclasses
from enum import Enum


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
