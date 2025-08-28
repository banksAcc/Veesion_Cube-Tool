"""BLE communication utilities for the capture application.

This module discovers and connects to a BLE device, relaying start and stop
commands between the hardware and the session manager. It also allows sending
arbitrary messages to the device through a queue.
"""

import asyncio
from bleak import BleakClient, BleakScanner

START_CMD = "START"
END_CMD = "END"  # user confirmed END


async def _discover_address(cfg: dict) -> str | None:
    """Find the BLE device address from the configuration or by scanning.

    Args:
        cfg (dict): Application configuration containing BLE options.

    Returns:
        str | None: Discovered device address or ``None`` if not found.

    Side Effects:
        Prints scan progress to stdout.
    """

    addr = cfg["ble"].get("addr")
    if addr:
        return addr
    name_prefix = cfg["ble"].get("name_prefix", "ESP32-RGB-BLE")
    timeout = float(cfg["ble"].get("scan_timeout", 6.0))
    print(f"[BLE] Scanning {timeout:.1f}s for '{name_prefix}*' ...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if d.name and d.name.startswith(name_prefix):
            print(f"[BLE] Found: {d.name} @ {d.address}")
            return d.address
    print("[BLE] No device found.")
    return None


async def run_ble_client(cfg: dict, session_mgr, out_queue: asyncio.Queue[str]):
    """Run the BLE client event loop.

    Args:
        cfg (dict): Application configuration.
        session_mgr: Session manager handling start/end commands.
        out_queue (asyncio.Queue[str]): Queue with outgoing messages for the
            BLE device.

    Returns:
        None

    Side Effects:
        Communicates with the BLE device and prints connection status.
    """

    address = await _discover_address(cfg)
    if not address:
        print("[BLE] No address: exiting.")
        return

    # UUID NUS TX (notifications from device to PC)
    NUS_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
    # UUID NUS RX (messages from PC to device)
    NUS_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

    async def on_notify(_handle, data: bytearray):
        """Handle notifications from the BLE device."""

        msg = data.decode(errors="ignore").strip().upper()
        if msg == START_CMD:
            await session_mgr.handle_start_command()
        elif msg == END_CMD or msg == "STOP":  # also accept "STOP"
            await session_mgr.handle_end_command()
        else:
            print(f"[BLE] Unknown message: {msg!r}")

    while True:
        try:
            print(f"[BLE] Connecting to {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                print(f"[BLE] Connected: {client.is_connected}")
                if not client.is_connected:
                    raise RuntimeError("Connection failed")

                await client.start_notify(NUS_TX_UUID, on_notify)
                print("[BLE] Subscribed to notifications. (CTRL+C to exit)")

                async def send_queued():
                    """Send messages from the queue to the BLE device."""

                    while True:
                        msg = await out_queue.get()
                        if msg is None:
                            break
                        try:
                            await client.write_gatt_char(NUS_RX_UUID, msg.encode())
                        except Exception as e:
                            print(f"[BLE] send error: {e}")

                sender_task = asyncio.create_task(send_queued())

                # Keep the connection alive; if it drops → stop capture if requested
                while client.is_connected:
                    await asyncio.sleep(0.5)

                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass

                print("[BLE] Disconnected.")
                if cfg["capture"].get("stop_on_ble_disconnect", True):
                    await session_mgr.stop_session(reason="ble_disconnect")

        except KeyboardInterrupt:
            print("\n[BLE] Interrupted by user.")
            return
        except Exception as e:
            print(f"[BLE] Error: {e}")

        print("[BLE] Retrying in 2s ...")
        await asyncio.sleep(2.0)
