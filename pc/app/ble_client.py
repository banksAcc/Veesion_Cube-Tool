
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

log = get_logger("BLE")


async def _discover_address(cfg: dict) -> str | None:
    """Find the BLE device address from the configuration or by scanning."""

    addr = cfg["ble"].get("addr")
    if addr:
        return addr
    name_prefix = cfg["ble"].get("name_prefix", "ESP32-RGB-BLE")
    timeout = float(cfg["ble"].get("scan_timeout", 6.0))
    log.info(f"Scanning {timeout:.1f}s for '{name_prefix}*' ...")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        if d.name and d.name.startswith(name_prefix):
            log.info(f"Found: {d.name} @ {d.address}")
            return d.address
    log.warning("No device found.")
    return None


async def run_ble_client(cfg: dict, session_mgr, out_queue: asyncio.Queue[str]):
    """Connect to the ESP32 and bridge BLE messages to the session manager."""

    address = await _discover_address(cfg)
    if not address:
        log.error("No address: exiting.")
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
        elif msg == END_CMD or msg == "STOP":  # accept also "STOP"
            await session_mgr.handle_end_command()
        else:
            log.warning(f"Unknown message: {msg!r}")

    while True:
        try:
            log.info(f"Connecting to {address} ...")
            async with BleakClient(address, timeout=10.0) as client:
                log.info(f"Connected: {client.is_connected}")
                if not client.is_connected:
                    raise RuntimeError("Connection failed")

                sender_task = None
                try:
                    await session_mgr.on_ble_connected()
                    await client.start_notify(NUS_TX_UUID, on_notify)
                    log.info("Subscribed to notifications. (CTRL+C to exit)")

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

                    # Keep the connection alive; session manager reacts if it drops
                    while client.is_connected:
                        await asyncio.sleep(0.5)
                finally:
                    if sender_task is not None:
                        sender_task.cancel()
                        try:
                            await sender_task
                        except asyncio.CancelledError:
                            pass
                    log.info("Disconnected.")
                    await session_mgr.on_ble_disconnected()
        except KeyboardInterrupt:
            log.info("Interrupted by user.")
            await session_mgr.on_ble_disconnected()
            return
        except Exception as e:
            log.error(f"Error: {e}")
            await session_mgr.on_ble_disconnected()

        log.info("Retrying in 2s ...")
        await asyncio.sleep(2.0)
