"""Simple BLE listener for deprecated ESP32 firmware example."""

# pip install bleak
import asyncio
import argparse
import sys
from bleak import BleakClient, BleakScanner

# On Windows some Python/bleak versions require WindowsSelectorEventLoop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Nordic UART Service (NUS) - TX UUID: notifications from device to PC
NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


async def find_device(name_prefix: str | None, address: str | None, scan_timeout: float = 6.0):
    """Return the BLE address for a device matching the given filters."""
    if address:
        return address
    print(f"[SCAN] BLE scan for {scan_timeout:.1f}s...")
    devices = await BleakScanner.discover(timeout=scan_timeout)
    for d in devices:
        if name_prefix and d.name and d.name.startswith(name_prefix):
            print(f"[SCAN] Found: {d.name} @ {d.address}")
            return d.address
    print("[SCAN] No compatible device found.")
    return None


async def listen_notifications(address: str):
    """Connect to the given address and print incoming notifications."""

    async def on_notify(_handle, data: bytearray):
        msg = data.decode(errors="ignore").strip()
        print(f"[RX] {msg}")

    while True:
        try:
            print(f"[BLE] Connecting to {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                ok = client.is_connected
                print(f"[BLE] Connected: {ok}")
                if not ok:
                    raise RuntimeError("Connection failed")

                await client.start_notify(NUS_TX_UUID, on_notify)
                print("[BLE] Listening for notifications on NUS/TX. (CTRL+C to exit)")

                while client.is_connected:
                    await asyncio.sleep(1.0)

                print("[BLE] Disconnected from device.")

        except KeyboardInterrupt:
            print("\n[BLE] Interrupted by user.")
            return
        except Exception as e:
            print(f"[BLE] Error: {e}")

        print("[BLE] Retrying in 2 seconds...")
        await asyncio.sleep(2.0)


async def main():
    """CLI entry point for the BLE notification listener."""
    parser = argparse.ArgumentParser(description="Listen to BLE notifications from an ESP32 (START/END).")
    parser.add_argument("--name", default="ESP32-RGB-BLE", help="Device name prefix (default: ESP32-RGB-BLE)")
    parser.add_argument("--addr", default=None, help="Device address (MAC on Linux/Android, GUID on Windows)")
    parser.add_argument("--scan", type=float, default=6.0, help="Scan duration in seconds (default: 6.0)")
    args = parser.parse_args()

    address = await find_device(args.name, args.addr, scan_timeout=args.scan)
    if not address:
        print("Tips:")
        print("- Hold the BLE button on the ESP32 to enter advertising (blue 'breathing' LED).")
        print("- Ensure the PC has BLE enabled/supported.")
        print("- Try increasing scan duration with --scan 10")
        return

    await listen_notifications(address)


if __name__ == "__main__":
    asyncio.run(main())
