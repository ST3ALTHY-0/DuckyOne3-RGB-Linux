#!/usr/bin/env python3
"""Discover Ducky HID interfaces and communicate with the bootloader on Linux."""
import os
from pathlib import Path
import select
import struct
import time

APROM_PID = 0x5311
LDROM_PID = 0x5310
HIDRAW_ROOT = Path("/sys/class/hidraw")
SYNC = struct.pack("<I", 1)


class ShortHIDWrite(OSError):
    """The kernel accepted fewer bytes than expected for a HID report."""


def find_device(pid, hidraw_root=HIDRAW_ROOT, dev_root=Path("/dev")):
    candidates = []

    for raw in hidraw_root.glob("hidraw*"):
        try:
            hid_device = (raw / "device").resolve()

            properties = dict(
                line.split("=", 1)
                for line in (hid_device / "uevent").read_text().splitlines()
                if "=" in line
            )

            bus, vendor, product = (
                int(value, 16)
                for value in properties["HID_ID"].split(":")
            )

            if bus != 0x0003:
                continue

            if vendor != 0x3233 or product != pid:
                continue

            # Locate the parent USB interface dynamically.
            interface = next(
                (
                    parent
                    for parent in hid_device.parents
                    if (parent / "bInterfaceNumber").exists()
                ),
                None
            )

            if interface is None:
                continue

            if (interface / "bInterfaceClass").read_text().strip() != "03":
                continue

            has_input = False
            has_output = False

            for endpoint in interface.glob("ep_*"):
                address = int(
                    (endpoint / "bEndpointAddress").read_text().strip(),
                    16
                )

                attributes = int(
                    (endpoint / "bmAttributes").read_text().strip(),
                    16
                )

                packet_size = int(
                    (endpoint / "wMaxPacketSize").read_text().strip(),
                    16
                )

                # Require a 64-byte interrupt endpoint.
                if (attributes & 0x03) != 0x03:
                    continue

                if (packet_size & 0x07FF) != 64:
                    continue

                if address & 0x80:
                    has_input = True
                else:
                    has_output = True

            if has_input and has_output:
                device = dev_root / raw.name

                if device.exists():
                    candidates.append(str(device))

        except (OSError, ValueError, KeyError):
            continue

    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple matching HID interfaces for "
            f"3233:{pid:04X}: {candidates}"
        )

    return candidates[0] if candidates else None


def wait_device(pid, seconds=10):
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        path = find_device(pid)
        if path:
            try:
                return path, os.open(path, os.O_RDWR | os.O_NONBLOCK)
            except OSError as exc:
                last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Could not open 3233:{pid:04x} within {seconds}s") from last_error


def reboot_payload(descriptor):
    """Select the reboot protocol from the first top-level collection usage."""
    page = None
    usage = None
    position = 0
    while position < len(descriptor):
        item = descriptor[position]
        position += 1
        size = (0, 1, 2, 4)[item & 3]
        if item == 0xFE or position + size > len(descriptor):
            break
        value = int.from_bytes(descriptor[position:position + size], "little")
        position += size
        tag = item & 0xFC
        if tag == 0x04:
            page = value
        elif tag == 0x08:
            usage = (value >> 16, value & 0xFFFF) if size == 4 else (page, value)
        elif tag == 0xA0:
            if value == 1 and usage == (0x0001, 0x0000):
                return b"\xcc".ljust(64, b"\0")
            if value == 1 and usage == (0xFF00, 0x0001):
                return bytes.fromhex("00 3A 01 09 01 04 00 01 01").ljust(64, b"\0")
            break
        elif item & 0x0C == 0:
            usage = None
    raise ValueError("Unrecognized APROM HID protocol")


def write_report(fd, payload):
    if len(payload) != 64:
        raise ValueError("Expected a 64-byte HID payload")
    written = os.write(fd, b"\x00" + payload)
    if written != 65:
        if written == 0:
            raise OSError("HID write transferred zero bytes")
        raise ShortHIDWrite(f"Short HID write: {written}/65 bytes")


def enter_ldrom(path, fd):
    descriptor = (HIDRAW_ROOT / Path(path).name / "device/report_descriptor").read_bytes()
    payload = reboot_payload(descriptor)
    protocol = "legacy" if payload[0] == 0xCC else "new"
    print(f"Requesting LDROM with the {protocol} APROM reboot protocol", flush=True)
    write_report(fd, payload)


def read_reply(fd, label, timeout=3):
    if not select.select([fd], [], [], timeout)[0]:
        raise TimeoutError(f"No reply to {label}")
    reply = os.read(fd, 64)
    if len(reply) != 64:
        raise RuntimeError(f"Short reply to {label}: {len(reply)}/64 bytes")
    return reply


def send(fd, command, data=b"", expect_reply=True):
    payload = bytearray(64)
    payload[0] = command
    payload[8:8 + len(data)] = data
    write_report(fd, payload)
    if expect_reply:
        return read_reply(fd, f"0x{command:02X}")


def check_seq(reply, expected):
    seq = struct.unpack_from("<I", reply, 4)[0]
    if seq != expected:
        raise RuntimeError(f"Unexpected packet number {seq}, expected {expected}")


def sync(fd):
    check_seq(send(fd, 0xA4, SYNC), 2)


def inspect_ldrom(fd):
    check_seq(send(fd, 0xAE), 2)
    sync(fd)
    version = send(fd, 0xA6)
    check_seq(version, 4)
    ident = send(fd, 0xB1)
    check_seq(ident, 6)
    config = send(fd, 0xA2)
    check_seq(config, 8)
    pid, = struct.unpack_from("<I", ident, 8)
    cfg0, cfg1 = struct.unpack_from("<II", config, 8)
    print(f"LDROM version=0x{version[8]:02X}; MCU=0x{pid:08X}; CONFIG0=0x{cfg0:08X}; CONFIG1=0x{cfg1:08X}")
    return version[8], pid, cfg0, cfg1


if __name__ == "__main__":
    # Import under the package name so the CLI uses the same shared transport.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from recovery.recover_usb import inspect_main

    inspect_main()
