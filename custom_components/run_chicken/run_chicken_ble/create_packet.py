"""Create packets for the Run-Chicken door."""

import datetime as dt
import struct

import crc8


def create_open_packet(packet_time: dt.datetime | None = None) -> bytes:
    """Create a packet for opening the Run-Chicken door."""
    return create_packet(open_door=True, close_door=False, packet_time=packet_time)


def create_close_packet(packet_time: dt.datetime | None = None) -> bytes:
    """Create a packet for closing the Run-Chicken door."""
    return create_packet(open_door=False, close_door=True, packet_time=packet_time)


def create_packet(*, open_door: bool, close_door: bool, packet_time: dt.datetime | None = None) -> bytes:
    """Create a packet for the Run-Chicken door."""
    # Ensure only one and only one door command is sent
    if open_door and close_door:
        msg = "Only one door command can be sent at a time."
        raise ValueError(msg)

    if not (open_door or close_door):
        msg = "One of open_door or close_door must be True."
        raise ValueError(msg)

    if packet_time is None:
        packet_time = dt.datetime.now(dt.UTC)

    crc = crc8.crc8()
    packet = bytes([0])  # Initial byte is 0x00 for sending a door command.
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
    packet += struct.pack("<B", 0x01 if open_door else 0x02)
    packet += struct.pack("<9x")

    # Add the CRC
    crc.update(packet)
    packet += struct.pack("<B", crc.digest()[0])

    return packet


if __name__ == "__main__":
    # Convert 4 ints of a Unix timestamp to a datetime object
    test_time = [233, 66, 38, 105]
    test_time = dt.datetime.fromtimestamp(int.from_bytes(bytes(test_time), byteorder="little"), tz=dt.UTC)
    unix_time = int(test_time.timestamp())

    packet = create_open_packet(packet_time=test_time)
