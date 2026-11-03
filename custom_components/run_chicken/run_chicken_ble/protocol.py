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

from .models import RunChickenDoorState, RunChickenSchedule

_LOGGER = logging.getLogger(__name__)

# GATT identifiers for the Run-Chicken door. The service UUIDs are documentary;
# Bleak resolves characteristics by their own UUID without needing them.
READ_SERVICE_UUID = "0000004f-cc7a-482a-984a-7f2ed5b3e58f"
READ_CHAR_UUID = "00000001-8e22-4541-9d4c-21edae82ed19"
WRITE_SERVICE_UUID = "00000000-cc7a-482a-984a-7f2ed5b3e58f"
WRITE_CHAR_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"


#: Schedule mode values the app shows as "Manual": 2 when set explicitly, 0 on
#: a door whose automation was never configured. 1 is sunrise/sunset.
MANUAL_MODES = frozenset({0, 2})


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

    #: Byte offset of the (raw, unscaled) battery value in a read payload.
    #: Linear in the battery voltage; see ``sensor.raw_to_volts`` for the scale.
    battery_offset: ClassVar[int] = 13

    #: Byte [0] 0xB5 marks a frame sent after a door movement (or a settings
    #: change); its battery byte appears to be the reading taken while the
    #: motor ran, i.e. under load. Other frame types carry the idle value,
    #: though readings taken while the motor runs can still sag.
    load_frame_types: ClassVar[frozenset[int]] = frozenset({0xB5})

    #: Minimum payload length carrying location and schedule settings.
    schedule_min_length: ClassVar[int] = 27

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

    def parse_battery_raw(self, payload: bytes | bytearray) -> tuple[int | None, bool]:
        """
        Return ``(raw, under_load)`` for the battery byte.

        ``raw`` is ``None`` for short payloads; ``under_load`` tells whether the
        frame type carries the reading taken while the motor ran.
        """
        if len(payload) <= self.battery_offset:
            return None, False
        return payload[self.battery_offset], payload[0] in self.load_frame_types

    def parse_schedule(self, payload: bytes | bytearray) -> RunChickenSchedule | None:
        """
        Decode location and schedule settings, if the payload carries them.

        Layout (T-50 FW 1.2.x, long payload): [1..4] door clock (unix, LE),
        [9..10] latitude and [11..12] longitude in whole degrees (int16 LE),
        [19]/[20] open/close mode, [21..22] open hh:mm UTC, [23..24] close hh:mm
        UTC, [25]/[26] open/close offset in minutes, [41] anti-pinch flag.
        Returns ``None`` for short payloads. Modes, offsets and anti-pinch do
        not depend on a stored location; latitude/longitude are ``None`` when
        none is stored (0/0), and times are ``None`` in manual mode or when
        the door reports 00:00.

        The door only recomputes its times after the morning opening, so the
        stored times are turned into their *next* occurrence after the door
        clock; between midnight and the opening this is the previous day's time
        applied to today, typically within a couple of minutes.
        """
        if len(payload) < self.schedule_min_length:
            return None
        lat, lon = struct.unpack_from("<hh", payload, 9)
        has_location = not (lat == 0 and lon == 0)
        open_mode, close_mode = payload[19], payload[20]
        door_clock = dt.datetime.fromtimestamp(struct.unpack_from("<I", payload, 1)[0], dt.UTC)

        def next_at(hour: int, minute: int) -> dt.datetime | None:
            if hour > 23 or minute > 59 or (hour == 0 and minute == 0):  # noqa: PLR2004
                return None
            candidate = door_clock.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= door_clock:
                candidate += dt.timedelta(days=1)
            return candidate

        anti_pinch_offset = 41
        anti_pinch = bool(payload[anti_pinch_offset]) if len(payload) > anti_pinch_offset else None

        # In manual mode the door does not operate on its own; any stored times
        # are leftovers from an earlier mode.
        open_time = None if open_mode in MANUAL_MODES else next_at(payload[21], payload[22])
        close_time = None if close_mode in MANUAL_MODES else next_at(payload[23], payload[24])
        # Right after an operation the door already reports the following day's
        # time, which can still lie a few minutes ahead of its clock. An open
        # door opens next only after it has closed, and vice versa.
        door_state = self.parse_door_state(payload)
        if open_time and close_time:
            if door_state is RunChickenDoorState.OPEN and open_time < close_time:
                open_time += dt.timedelta(days=1)
            elif door_state is RunChickenDoorState.CLOSED and close_time < open_time:
                close_time += dt.timedelta(days=1)

        return RunChickenSchedule(
            latitude=lat if has_location else None,
            longitude=lon if has_location else None,
            open_mode=open_mode,
            close_mode=close_mode,
            open_time=open_time,
            close_time=close_time,
            open_offset=payload[25],
            close_offset=payload[26],
            anti_pinch=anti_pinch,
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
