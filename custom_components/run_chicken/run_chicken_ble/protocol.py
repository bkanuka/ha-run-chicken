"""
Per-model command-frame protocols for the Run-Chicken door.

Different door models speak slightly different command-frame formats. Each model
is represented by a `RunChickenProtocol` subclass that knows how to build its
own packets; the right protocol is chosen from the BLE advertised name.
"""

from __future__ import annotations

import abc
import datetime as dt
import struct
from enum import IntEnum
from typing import ClassVar

import crc8


class RunChickenAction(IntEnum):
    """Door action encoded in a command frame (byte [21])."""

    STATUS = 0x00  # Session-init / status, performs no movement.
    OPEN = 0x01
    CLOSE = 0x02


def _with_crc(packet: bytes) -> bytes:
    """Return ``packet`` with its trailing CRC-8 byte appended."""
    crc = crc8.crc8()
    crc.update(packet)
    return packet + struct.pack("<B", crc.digest()[0])


class RunChickenProtocol(abc.ABC):
    """Builds command frames for a particular Run-Chicken door model."""

    #: Human-readable model name, surfaced in the device registry.
    model: ClassVar[str]

    #: Whether the model expects a session-init "hello" once after connecting.
    needs_session_init: ClassVar[bool] = False

    @classmethod
    def for_advertised_name(cls, name: str | None) -> RunChickenProtocol:
        """
        Pick the protocol from the BLE advertised name.

        The GIANT advertises as ``G-<n>`` (e.g. ``G-90``); everything else is
        treated as a T-50, the safe default for unknown advertisements.
        """
        if name and name.upper().startswith("G-"):
            return GiantProtocol()
        return T50Protocol()

    def create_open_packet(self, packet_time: dt.datetime | None = None) -> bytes:
        """Create a packet for opening the door."""
        return self._build(RunChickenAction.OPEN, packet_time=self._resolve_time(packet_time))

    def create_close_packet(self, packet_time: dt.datetime | None = None) -> bytes:
        """Create a packet for closing the door."""
        return self._build(RunChickenAction.CLOSE, packet_time=self._resolve_time(packet_time))

    def create_session_init_packet(self, packet_time: dt.datetime | None = None) -> bytes:
        """Create the session-init "hello" packet sent once after connecting."""
        return self._build(RunChickenAction.STATUS, packet_time=self._resolve_time(packet_time), first=True)

    @staticmethod
    def _resolve_time(packet_time: dt.datetime | None) -> dt.datetime:
        """Default a missing timestamp to the current UTC time."""
        return packet_time if packet_time is not None else dt.datetime.now(dt.UTC)

    @abc.abstractmethod
    def _build(self, action: RunChickenAction, *, packet_time: dt.datetime, first: bool = False) -> bytes:
        """Build the raw command frame for ``action`` (including its CRC)."""


class T50Protocol(RunChickenProtocol):
    """
    T-50 command-frame protocol.

    The T-50 duplicates the timestamp and embeds the UTC hour/minute; the CRC-8
    covers the whole 31-byte body. It does not use a session-init packet.
    """

    model = "T-50"

    def _build(self, action: RunChickenAction, *, packet_time: dt.datetime, first: bool = False) -> bytes:
        packet = bytes([0x01 if first else 0x00])  # 0x00 for a normal door command.
        unix_time = int(packet_time.timestamp())

        # Unix timestamp
        packet += struct.pack("<I", unix_time)
        packet += struct.pack("<I", unix_time)  # Repeat the timestamp for some reason
        packet += struct.pack("<6x")

        # Add the UTC hour
        packet += struct.pack("<B", packet_time.hour)
        packet += struct.pack("<B", packet_time.minute)
        packet += struct.pack("<B", packet_time.hour)
        packet += struct.pack("<B", packet_time.minute)
        packet += struct.pack("<2x")

        # Open or close the door
        packet += struct.pack("<B", action)
        packet += struct.pack("<9x")

        return _with_crc(packet)


class GiantProtocol(RunChickenProtocol):
    """
    GIANT command-frame protocol.

    Simpler frame than the T-50: the duplicated timestamp and the hour/minute
    fields must be zero, and byte [0] is 0x01 only on the first (session-init)
    packet after connecting. The CRC-8 covers bytes [0..30].
    """

    model = "GIANT"
    needs_session_init = True

    def _build(self, action: RunChickenAction, *, packet_time: dt.datetime, first: bool = False) -> bytes:
        packet = bytes([0x01 if first else 0x00])
        packet += struct.pack("<I", int(packet_time.timestamp()))
        packet += struct.pack("<16x")
        packet += struct.pack("<B", action)
        packet += struct.pack("<9x")

        return _with_crc(packet)
