"""BLE communication utilities for the capture application.

This module discovers and connects to a BLE device, relaying start and stop
commands between the hardware and the session manager. It also allows sending
arbitrary messages to the device through a queue.
"""

import asyncio
from bleak import BleakClient, BleakScanner

from logger import get_logger

START_CMD = "START"
END_CMD = "END"  # user confirmed END

<<<<<<< HEAD

async def _discover_address(cfg: dict) -> str | None:
    """Find the BLE device address from the configuration or by scanning.

    Args:
        cfg (dict): Application configuration containing BLE options.

    Returns:
        str | None: Discovered device address or ``None`` if not found.

    Side Effects:
        Prints scan progress to stdout.
    """

=======
log = get_logger("BLE")

async def _discover_address(cfg: dict) -> str | None:
    """Return address from config or discover a device matching the name prefix."""
>>>>>>> main
    addr = cfg["ble"].get("addr")
    if addr:
        return addr
    name_prefix = cfg["ble"].get("name_prefix", "ESP32-RGB-BLE")
    timeout = float(cfg["ble"].get("scan_timeout", 6.0))
<<<<<<< HEAD
    print(f"[BLE] Scanning {timeout:.1f}s for '{name_prefix}*' ...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if d.name and d.name.startswith(name_prefix):
            print(f"[BLE] Found: {d.name} @ {d.address}")
            return d.address
    print("[BLE] No device found.")
=======
    log.info(f"Scanning {timeout:.1f}s for '{name_prefix}*' ...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if d.name and d.name.startswith(name_prefix):
            log.info(f"Found: {d.name} @ {d.address}")
            return d.address
    log.warning("No device found.")
>>>>>>> main
    return None


async def run_ble_client(cfg: dict, session_mgr, out_queue: asyncio.Queue[str]):
<<<<<<< HEAD
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
=======
    """Connect to the ESP32 and bridge BLE messages to the session manager."""
    address = await _discover_address(cfg)
    if not address:
        log.error("No address: exiting.")

>>>>>>> main
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
<<<<<<< HEAD
        elif msg == END_CMD or msg == "STOP":  # also accept "STOP"
            await session_mgr.handle_end_command()
        else:
            print(f"[BLE] Unknown message: {msg!r}")

    while True:
        try:
            print(f"[BLE] Connecting to {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                print(f"[BLE] Connected: {client.is_connected}")
=======
        elif msg == END_CMD or msg == "STOP":  # accept also "STOP"
            await session_mgr.handle_end_command()
        else:
            log.warning(f"Unknown message: {msg!r}")

    while True:
        try:
            log.info(f"Connecting to {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                log.info(f"Connected: {client.is_connected}")
>>>>>>> main
                if not client.is_connected:
                    raise RuntimeError("Connection failed")

                await client.start_notify(NUS_TX_UUID, on_notify)
<<<<<<< HEAD
                print("[BLE] Subscribed to notifications. (CTRL+C to exit)")
=======
                log.info("Subscribed to notifications. (CTRL+C to exit)")
>>>>>>> main

                async def send_queued():
                    """Send messages from the queue to the BLE device."""

                    while True:
                        msg = await out_queue.get()
                        if msg is None:
                            break
                        try:
                            await client.write_gatt_char(NUS_RX_UUID, msg.encode())
                        except Exception as e:
                            log.error(f"send error: {e}")

                sender_task = asyncio.create_task(send_queued())

<<<<<<< HEAD
                # Keep the connection alive; if it drops → stop capture if requested
=======
                # Keep the connection alive; stop capture if it drops
>>>>>>> main
                while client.is_connected:
                    await asyncio.sleep(0.5)

                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
<<<<<<< HEAD

                print("[BLE] Disconnected.")
=======
                log.info("Disconnected.")
>>>>>>> main
                if cfg["capture"].get("stop_on_ble_disconnect", True):
                    await session_mgr.stop_session(reason="ble_disconnect")

        except KeyboardInterrupt:
<<<<<<< HEAD
            print("\n[BLE] Interrupted by user.")
            return
        except Exception as e:
            print(f"[BLE] Error: {e}")

        print("[BLE] Retrying in 2s ...")
=======
            log.info("Interrupted by user.")
            return
        except Exception as e:
            log.error(f"Error: {e}")

        log.info("Retrying in 2s ...")
>>>>>>> main
        await asyncio.sleep(2.0)
