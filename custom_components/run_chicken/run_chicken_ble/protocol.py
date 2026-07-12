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

from .models import (
    RunChickenDeviceData,
    RunChickenDoorState,
    RunChickenMotorMode,
    RunChickenScheduleMode,
)

_LOGGER = logging.getLogger(__name__)

# GATT identifiers for the Run-Chicken door. The service UUIDs are documentary;
# Bleak resolves characteristics by their own UUID without needing them.
READ_SERVICE_UUID = "0000004f-cc7a-482a-984a-7f2ed5b3e58f"
READ_CHAR_UUID = "00000001-8e22-4541-9d4c-21edae82ed19"
WRITE_SERVICE_UUID = "00000000-cc7a-482a-984a-7f2ed5b3e58f"
WRITE_CHAR_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"

# 0000fe11-8e22-4541-9d4c-21edae82ed19 also exists on this device, under the
# write service, with properties ['write-without-response'] (no read/notify).
# Reportedly used for firmware update (FUS) / OTA transfer on this chipset
# family - DO NOT write to it. An undocumented/guessed write here risks
# corrupting or bricking the door's firmware, not just misbehaving. Not
# defined as a constant here on purpose, to avoid tempting future use.


class RunChickenAction(IntEnum):
    """Door action encoded in a command frame (byte [21])."""

    STATUS = 0x00  # Session-init / status, performs no movement.
    OPEN = 0x01
    CLOSE = 0x02


class RunChickenProtocol(abc.ABC):
    """Builds command frames for and decodes responses from a Run-Chicken door model."""

    #: Human-readable model name, surfaced in the device registry.
    model: ClassVar[str]

    #: Whether this model's settings-write frame (motor mode + open/close
    #: schedule) has been reverse-engineered. Only the T-50 family has, so
    #: settings entities stay read-only for any other model.
    supports_settings_write: ClassVar[bool] = False

    #: Byte offset of the door-state field in a read-characteristic payload.
    door_state_offset: ClassVar[int] = 17

    #: Byte offset of the battery voltage: a little-endian uint16 in centivolts
    #: (value / 100 = volts). Reverse-engineered from an nRF Sniffer capture -
    #: it read 290 (2.90V) at rest and sagged to 277 (2.77V) mid-open under
    #: motor load, matching the app's own displayed voltage at both points.
    battery_voltage_offset: ClassVar[int] = 13

    #: Remaining offsets below were reverse-engineered by capturing raw status
    #: payloads (via the integration's own raw-byte debug recorder) and
    #: diffing them against known app settings changes and app-reported
    #: values - there is no official protocol spec. Verified against T-50
    #: family doors (including "Eternal BT"); not verified on GIANT, which is
    #: known to use a different command-frame layout (see issue #12) and may
    #: differ here too.
    open_schedule_mode_offset: ClassVar[int] = 19
    close_schedule_mode_offset: ClassVar[int] = 20
    #: 2 bytes: resolved open time as (hour, minute), UTC. Populated by
    #: whichever schedule mode is active - a fixed Timer setting, or the
    #: day's resolved Sunrise/Sunset+offset time.
    open_time_offset: ClassVar[int] = 21
    #: 2 bytes: resolved close time as (hour, minute), UTC - same shape as
    #: open_time_offset, by symmetry with the open_schedule_mode_offset /
    #: close_schedule_mode_offset pairing. Confirmed against a real Close->Time
    #: app setting (21:00 local read back here as 01:00 UTC).
    close_time_offset: ClassVar[int] = 23
    open_offset_minutes_offset: ClassVar[int] = 25
    close_offset_minutes_offset: ClassVar[int] = 26
    #: 3 bytes: firmware version as (major, minor, patch).
    firmware_version_offset: ClassVar[int] = 38
    motor_mode_offset: ClassVar[int] = 41

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

    def settings_packet(
        self,
        current: RunChickenDeviceData,
        *,
        motor_mode: RunChickenMotorMode | None = None,
        open_schedule_mode: RunChickenScheduleMode | None = None,
        close_schedule_mode: RunChickenScheduleMode | None = None,
        open_time: dt.time | None = None,
        close_time: dt.time | None = None,
        open_offset_minutes: int | None = None,
        close_offset_minutes: int | None = None,
        packet_time: dt.datetime | None = None,
    ) -> bytes:
        """
        Build a settings-write frame, changing only the fields passed and
        preserving everything else from ``current``.

        The door's settings command is a full read-modify-write blob: one frame
        carries the motor mode *and* the entire open/close schedule at once, so
        every field must be supplied. Any field left as ``None`` is taken from
        ``current`` (the latest polled snapshot); pass a field to change it.
        Times are UTC, matching how the door stores and reports them.

        Raises ``ValueError`` if any resulting field is still unknown (e.g. the
        current snapshot never resolved a schedule mode), rather than writing a
        frame that would silently wipe a real setting to a default.
        """
        motor_mode = current.motor_mode if motor_mode is None else motor_mode
        open_schedule_mode = current.open_schedule_mode if open_schedule_mode is None else open_schedule_mode
        close_schedule_mode = current.close_schedule_mode if close_schedule_mode is None else close_schedule_mode
        open_time = current.open_time if open_time is None else open_time
        close_time = current.close_time if close_time is None else close_time
        open_offset_minutes = current.open_offset_minutes if open_offset_minutes is None else open_offset_minutes
        close_offset_minutes = current.close_offset_minutes if close_offset_minutes is None else close_offset_minutes

        unknown = [
            name
            for name, known in (
                ("motor mode", motor_mode not in (None, RunChickenMotorMode.UNKNOWN)),
                ("open schedule mode", open_schedule_mode not in (None, RunChickenScheduleMode.UNKNOWN)),
                ("close schedule mode", close_schedule_mode not in (None, RunChickenScheduleMode.UNKNOWN)),
                ("open time", open_time is not None),
                ("close time", close_time is not None),
                ("open offset minutes", open_offset_minutes is not None),
                ("close offset minutes", close_offset_minutes is not None),
            )
            if not known
        ]
        if unknown:
            msg = (
                "Cannot change door settings while these values are still unknown: "
                f"{', '.join(unknown)}. Wait for a reading from the door and try again."
            )
            raise ValueError(msg)

        return self._build_settings(
            motor_mode=motor_mode,
            open_schedule_mode=open_schedule_mode,
            close_schedule_mode=close_schedule_mode,
            open_time=open_time,
            close_time=close_time,
            open_offset_minutes=open_offset_minutes,
            close_offset_minutes=close_offset_minutes,
            packet_time=self._resolve_time(packet_time),
        )

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

    def parse_status(self, payload: bytes | bytearray) -> RunChickenDeviceData:
        """Decode a full status snapshot from a read-characteristic payload."""
        return RunChickenDeviceData(
            door_state=self.parse_door_state(payload),
            firmware_version=self._parse_firmware_version(payload),
            battery_voltage=self._parse_battery_voltage(payload),
            motor_mode=self._parse_enum(payload, self.motor_mode_offset, RunChickenMotorMode),
            open_schedule_mode=self._parse_enum(payload, self.open_schedule_mode_offset, RunChickenScheduleMode),
            close_schedule_mode=self._parse_enum(payload, self.close_schedule_mode_offset, RunChickenScheduleMode),
            open_offset_minutes=self._parse_byte(payload, self.open_offset_minutes_offset),
            close_offset_minutes=self._parse_byte(payload, self.close_offset_minutes_offset),
            open_time=self._parse_time(payload, self.open_time_offset),
            close_time=self._parse_time(payload, self.close_time_offset),
        )

    @staticmethod
    def _parse_byte(payload: bytes | bytearray, offset: int) -> int | None:
        """Return the byte at ``offset``, or None if the payload is too short."""
        return payload[offset] if len(payload) > offset else None

    @classmethod
    def _parse_enum(cls, payload: bytes | bytearray, offset: int, enum_cls: type) -> object:
        """Decode a single-byte enum field, falling back to the enum's UNKNOWN member."""
        value = cls._parse_byte(payload, offset)
        if value is None:
            return enum_cls.UNKNOWN
        try:
            return enum_cls(value)
        except ValueError:
            return enum_cls.UNKNOWN

    @staticmethod
    def _parse_time(payload: bytes | bytearray, offset: int) -> dt.time | None:
        """Decode a resolved (hour, minute) field at ``offset`` as a UTC ``time``."""
        if len(payload) <= offset + 1:
            return None
        hour, minute = payload[offset], payload[offset + 1]
        if hour > 23 or minute > 59:  # noqa: PLR2004
            return None
        return dt.time(hour, minute, tzinfo=dt.UTC)

    def _parse_battery_voltage(self, payload: bytes | bytearray) -> float | None:
        """Decode battery voltage from the little-endian centivolt field, in volts."""
        offset = self.battery_voltage_offset
        if len(payload) <= offset + 1:
            return None
        centivolts = payload[offset] | (payload[offset + 1] << 8)
        return centivolts / 100

    def _parse_firmware_version(self, payload: bytes | bytearray) -> str | None:
        """Decode the 3-byte (major, minor, patch) firmware version, e.g. "1.2.56"."""
        if len(payload) <= self.firmware_version_offset + 2:
            return None
        major, minor, patch = payload[self.firmware_version_offset : self.firmware_version_offset + 3]
        return f"{major}.{minor}.{patch}"

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

    def _build_settings(
        self,
        *,
        motor_mode: RunChickenMotorMode,
        open_schedule_mode: RunChickenScheduleMode,
        close_schedule_mode: RunChickenScheduleMode,
        open_time: dt.time,
        close_time: dt.time,
        open_offset_minutes: int,
        close_offset_minutes: int,
        packet_time: dt.datetime,
    ) -> bytes:
        """
        Build the model's settings-write frame (validated inputs only).

        Only overridden by models whose settings frame is known; the default
        refuses, guarded by ``supports_settings_write``.
        """
        msg = f"Writing settings is not supported for the {self.model}."
        raise NotImplementedError(msg)


class T50Protocol(RunChickenProtocol):
    """
    T-50 command-frame protocol.

    The T-50 duplicates the timestamp and embeds the UTC hour/minute; the CRC-8
    covers the whole 31-byte body.
    """

    model = "T-50"
    supports_settings_write = True

    #: Bytes [9..12] of the settings frame. Every settings write the official
    #: app sent carried this exact value (across motor-mode and schedule
    #: changes); its meaning is unconfirmed, but the door accepts it as a fixed
    #: header. Reverse-engineered from an nRF Sniffer capture of the app.
    _SETTINGS_HEADER: ClassVar[bytes] = bytes.fromhex("2800b4ff")

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

    def _build_settings(
        self,
        *,
        motor_mode: RunChickenMotorMode,
        open_schedule_mode: RunChickenScheduleMode,
        close_schedule_mode: RunChickenScheduleMode,
        open_time: dt.time,
        close_time: dt.time,
        open_offset_minutes: int,
        close_offset_minutes: int,
        packet_time: dt.datetime,
    ) -> bytes:
        # Settings frame (byte [0] = 0x00). Unlike the open/close frame it does
        # not duplicate the timestamp, and it packs the whole open/close
        # schedule into bytes [13..20]. Byte [21] is held at STATUS so the door
        # applies the settings without moving; byte [22] carries the motor mode.
        packet = bytearray(31)
        struct.pack_into("<I", packet, 1, int(packet_time.timestamp()))
        packet[9:13] = self._SETTINGS_HEADER
        packet[13] = open_schedule_mode.value
        packet[14] = close_schedule_mode.value
        packet[15] = open_time.hour
        packet[16] = open_time.minute
        packet[17] = close_time.hour
        packet[18] = close_time.minute
        packet[19] = open_offset_minutes
        packet[20] = close_offset_minutes
        packet[21] = RunChickenAction.STATUS
        packet[22] = motor_mode.value
        return self._append_crc(bytes(packet))


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
