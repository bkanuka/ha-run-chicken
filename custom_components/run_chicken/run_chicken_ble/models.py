from __future__ import annotations

import dataclasses
import datetime as dt
from enum import Enum


class RunChickenDoorState(Enum):
    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2

@dataclasses.dataclass
class RunChickenDeviceData:
    """Response data with information about the RunChicken device."""

    model: str | None = "T-50"
    manufacturer: str | None = "Run-Chicken"
    name: str = ""
    identifier: str = ""
    address: str = ""
    door_state: RunChickenDoorState = RunChickenDoorState.UNKNOWN

    values: dict[str, int | float] = dataclasses.field(default_factory=dict)

    def friendly_name(self) -> str:
        """Generate a name for the device."""
        return f"Run-Chicken Door {self.name}"


@dataclasses.dataclass
class RunChickenDeviceUpdate:
    door_state: RunChickenDoorState
    datetime: dt.datetime = dt.datetime.now(tz=dt.UTC)

