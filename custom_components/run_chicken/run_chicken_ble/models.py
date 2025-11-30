from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Optional
import datetime as dt


class RunChickenDoorState(Enum):
    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2


@dataclasses.dataclass
class RunChickenDevice:
    """ Response data with information about the RunChicken device. """

    model: Optional[str] = "T-50"
    name: str = ""
    identifier: str = ""
    address: str = ""
    door_state: RunChickenDoorState = RunChickenDoorState.UNKNOWN

    values: dict[str, int | float] = dataclasses.field(default_factory=dict)

    def friendly_name(self) -> str:
        """Generate a name for the device."""
        return f"Chicken-Run Door {self.name}"


@dataclasses.dataclass
class RunChickenDeviceUpdate:
    door_state: RunChickenDoorState
    datetime: dt.datetime = dt.datetime.now(tz=dt.timezone.utc)

