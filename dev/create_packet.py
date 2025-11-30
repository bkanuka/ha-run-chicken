import crc8
import struct
import datetime as dt


def create_packet(open_door: bool = False, close_door: bool = False, packet_time: dt.datetime = None) -> bytes:
    """Create a packet for the Run-Chicken door."""

    # Ensure only one and only one door command is sent
    try:
        assert not (open_door and close_door)
    except AssertionError:
        raise ValueError("Only one door command can be sent at a time.")

    try:
        assert open_door or close_door
    except AssertionError:
        raise ValueError("One of open_door or close_door must be True.")

    if packet_time is None:
        packet_time = dt.datetime.now()

    crc = crc8.crc8()
    packet = bytes([0])  # Initial byte is 0x00 for sending a door command. 0x00 if just updating the time.
    unix_time = int(packet_time.timestamp())

    # Unix timestamp
    packet += struct.pack('<I', unix_time)
    packet += struct.pack('<I', unix_time)  # Repeat the timestamp for some reason
    packet += struct.pack('<6x')

    # Add the UTC hour
    print(packet_time.hour, packet_time.minute)
    packet += struct.pack('<B', packet_time.hour)
    packet += struct.pack('<B', packet_time.minute)
    packet += struct.pack('<B', packet_time.hour)
    packet += struct.pack('<B', packet_time.minute)
    packet += struct.pack('<2x')

    # Open or close the door
    packet += struct.pack('<B', 0x01 if open_door else 0x02)
    packet += struct.pack('<9x')

    # Add the CRC
    crc.update(packet)
    packet += struct.pack('<B', crc.digest()[0])

    return packet


if __name__ == '__main__':

    # Convert 4 ints of a Unix timestamp to a datetime object
    test_time = [233, 66, 38, 105]
    test_time = dt.datetime.fromtimestamp(
        int.from_bytes(bytes(test_time), byteorder='little'), tz=dt.timezone.utc
    )
    unix_time = int(test_time.timestamp())

    packet = create_packet(open_door=True, packet_time=test_time)
    print(packet.hex())