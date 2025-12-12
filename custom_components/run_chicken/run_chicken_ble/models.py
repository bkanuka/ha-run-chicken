"""Models for RunChicken BLE integration."""

from __future__ import annotations

import dataclasses
from enum import Enum


class RunChickenDoorState(Enum):
    """Possible states of the RunChicken door."""

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
