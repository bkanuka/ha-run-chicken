"""
Per-model command-frame protocols for the Run-Chicken door.

Different door models speak slightly different command-frame formats. Each model
is represented by a `RunChickenProtocol` subclass that knows how to build its own
packets and decode the door's responses; the right protocol is chosen from the
BLE advertised name. This module also owns the GATT characteristic identifiers
the door exposes.
"""

from __future__ import annotations

import abc
import datetime as dt
import logging
import struct
from enum import IntEnum
from typing import ClassVar

import crc8

from .models import RunChickenDoorState

_LOGGER = logging.getLogger(__name__)

# GATT identifiers for the Run-Chicken door. The service UUIDs are documentary;
# Bleak resolves characteristics by their own UUID without needing them.
READ_SERVICE_UUID = "0000004f-cc7a-482a-984a-7f2ed5b3e58f"
READ_CHAR_UUID = "00000001-8e22-4541-9d4c-21edae82ed19"
WRITE_SERVICE_UUID = "00000000-cc7a-482a-984a-7f2ed5b3e58f"
WRITE_CHAR_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"


class RunChickenAction(IntEnum):
    """Door action encoded in a command frame (byte [21])."""

    STATUS = 0x00  # Session-init / status, performs no movement.
    OPEN = 0x01
    CLOSE = 0x02


class RunChickenProtocol(abc.ABC):
    """Builds command frames for and decodes responses from a Run-Chicken door model."""

    #: Human-readable model name, surfaced in the device registry.
    model: ClassVar[str]

    #: Byte offset of the door-state field in a read-characteristic payload.
    door_state_offset: ClassVar[int] = 17

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

    def open_packet(self, packet_time: dt.datetime | None = None) -> bytes:
        """Create a packet for opening the door."""
        return self._build(RunChickenAction.OPEN, self._resolve_time(packet_time))

    def close_packet(self, packet_time: dt.datetime | None = None) -> bytes:
        """Create a packet for closing the door."""
        return self._build(RunChickenAction.CLOSE, self._resolve_time(packet_time))

    def session_init_packet(self, packet_time: dt.datetime | None = None) -> bytes:
        """Create the session-init "hello" packet sent once after connecting."""
        return self._build(RunChickenAction.STATUS, self._resolve_time(packet_time))

    def parse_door_state(self, payload: bytes | bytearray) -> RunChickenDoorState:
        """
        Decode the door state from a read-characteristic payload.

        The state is a single byte at ``door_state_offset`` (0 = open,
        1 = closed); a short or unrecognised payload reads as ``UNKNOWN``.
        """
        _LOGGER.debug("Parsing payload: %s", payload.hex())
        if len(payload) <= self.door_state_offset:
            _LOGGER.warning("Payload too short to contain door state: %s", payload.hex())
            return RunChickenDoorState.UNKNOWN
        return {0: RunChickenDoorState.OPEN, 1: RunChickenDoorState.CLOSED}.get(
            payload[self.door_state_offset], RunChickenDoorState.UNKNOWN
        )

    @staticmethod
    def _resolve_time(packet_time: dt.datetime | None) -> dt.datetime:
        """Default a missing timestamp to the current UTC time."""
        return packet_time if packet_time is not None else dt.datetime.now(dt.UTC)

    @staticmethod
    def _append_crc(packet: bytes) -> bytes:
        """Return ``packet`` with its trailing CRC-8 byte appended."""
        crc = crc8.crc8()
        crc.update(packet)
        return packet + struct.pack("<B", crc.digest()[0])

    @abc.abstractmethod
    def _build(self, action: RunChickenAction, packet_time: dt.datetime) -> bytes:
        """
        Build the raw command frame for ``action`` (including its CRC).

        The frame is stamped with ``packet_time``, and byte [0] is 0x01 for the
        session-init/status frame (``action`` is ``STATUS``) or 0x00 for a door
        command.
        """


class T50Protocol(RunChickenProtocol):
    """
    T-50 command-frame protocol.

    The T-50 duplicates the timestamp and embeds the UTC hour/minute; the CRC-8
    covers the whole 31-byte body.
    """

    model = "T-50"

    def _build(self, action: RunChickenAction, packet_time: dt.datetime) -> bytes:
        # Byte [0] is 0x01 for the session-init/status frame, 0x00 for a command.
        packet = bytes([0x01 if action is RunChickenAction.STATUS else 0x00])
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

        return self._append_crc(packet)


class GiantProtocol(RunChickenProtocol):
    """
    GIANT command-frame protocol.

    Simpler frame than the T-50: the duplicated timestamp and the hour/minute
    fields must be zero, and byte [0] is 0x01 only on the first (session-init)
    packet after connecting. The CRC-8 covers bytes [0..30].
    """

    model = "GIANT"

    def _build(self, action: RunChickenAction, packet_time: dt.datetime) -> bytes:
        # Byte [0] is 0x01 for the session-init/status frame, 0x00 for a command.
        packet = bytes([0x01 if action is RunChickenAction.STATUS else 0x00])
        packet += struct.pack("<I", int(packet_time.timestamp()))
        packet += struct.pack("<16x")
        packet += struct.pack("<B", action)
        packet += struct.pack("<9x")

        return self._append_crc(packet)
