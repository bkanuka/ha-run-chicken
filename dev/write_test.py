import asyncio
from bleak import BleakClient
from create_packet import create_packet

SERVICE_UUID = '00000000-cc7a-482a-984a-7f2ed5b3e58f'
ADDR = "00:80:e1:22:43:0d"
CHARACTERISTIC_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"


async def main(open_door: bool = False, close_door: bool = False):
    async with BleakClient(ADDR) as client:
        packet = create_packet(open_door=open_door, close_door=close_door)
        await client.write_gatt_char(CHARACTERISTIC_UUID, packet)
        print("Write successful. Waiting for door...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(
        main(
            open_door=True,
            close_door=False
        ))