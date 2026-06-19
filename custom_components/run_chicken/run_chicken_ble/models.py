"""Models for RunChicken BLE integration."""

from __future__ import annotations

import dataclasses
from enum import Enum


class RunChickenDoorState(Enum):
    """Possible states of the RunChicken door."""

    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2

    @classmethod
    def from_raw(cls, raw: int) -> RunChickenDoorState:
        """Map the device's raw door-state byte (0 = open, 1 = closed) to a state."""
        return {0: cls.OPEN, 1: cls.CLOSED}.get(raw, cls.UNKNOWN)


@dataclasses.dataclass
class RunChickenDeviceData:
    """Response data with information about the RunChicken device."""

    model: str | None = "T-50"
    manufacturer: str | None = "Run-Chicken"
    name: str = ""
    identifier: str = ""
    address: str = ""
    door_state: RunChickenDoorState = RunChickenDoorState.UNKNOWN

    def friendly_name(self) -> str:
        """Generate a name for the device."""
        return f"Run-Chicken Door {self.name}"
