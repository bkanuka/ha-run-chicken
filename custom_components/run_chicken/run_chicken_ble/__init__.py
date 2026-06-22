"""
Run-Chicken BLE package.

Helpers for interacting with Run-Chicken devices over Bluetooth Low Energy
(BLE). The package exposes a small public API for parsing device payloads and
representing the parsed data:

- `RunChickenDevice` — BLE interface for sending commands and reading payloads
- `RunChickenDeviceData` — immutable snapshot of the door's observed state

Safe to import: no side effects at import time. The explicit `__all__`
defines the public surface of the package.
"""

from .device import RunChickenDevice
from .models import RunChickenDeviceData

__all__ = [
    "RunChickenDevice",
    "RunChickenDeviceData",
]
