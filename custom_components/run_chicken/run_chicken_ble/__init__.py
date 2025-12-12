"""
Run-Chicken BLE package.

Helpers for interacting with Run-Chicken devices over Bluetooth Low Energy
(BLE). The package exposes a small public API for parsing device payloads and
representing the parsed data:

- `RunChickenDevice` — parser/codec for device payloads
- `RunChickenDeviceData` — structured data model for parsed values

Safe to import: no side effects at import time. The explicit `__all__`
defines the public surface of the package.
"""

from .models import RunChickenDeviceData
from .parser import RunChickenDevice

__all__ = [
    "RunChickenDevice",
    "RunChickenDeviceData",
]
