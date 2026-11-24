#!/usr/bin/env python3
"""Inspect or restore the Ducky One 3 SF RGB over Linux USB HID."""
import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import struct
import sys

if __package__:
    from . import inspect_ducky_ldrom as hid
else:
    import inspect_ducky_ldrom as hid


@dataclass(frozen=True)
class FirmwareProfile:
    name: str
    size: int
    sha256: str
    confirmation: str
    identity: tuple[int, int, int, int]


# LDROM version, MCU product ID, CONFIG0, CONFIG1 on the verified keyboard.
VERIFIED_IDENTITY = (0x33, 0x01205212, 0xF7FFFF7C, 0x00033200)
STOCK = FirmwareProfile(
    "stock V1.16", 42942,
    "966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844",
    "RESTORE-DUCKY-1.16", VERIFIED_IDENTITY,
)
V3 = FirmwareProfile(
    "modified V3", 43084,
    "78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258",
    "FLASH-DUCKY-V3", VERIFIED_IDENTITY,
)


def verify_image(firmware, profile):
    digest = hashlib.sha256(firmware).hexdigest()
    if len(firmware) != profile.size or digest != profile.sha256:
        raise ValueError(f"Firmware does not match the verified {profile.name} image")
    return digest


def build_packets(firmware):
    first = bytearray(64)
    first[0] = 0xA0
    struct.pack_into("<I", first, 12, len(firmware))
    first_data = firmware[:48]
    first[16:16 + len(first_data)] = first_data
    packets = [bytes(first)]
    for pos in range(48, len(firmware), 56):
        packets.append((b"\0" * 8 + firmware[pos:pos + 56]).ljust(64, b"\0"))
    return packets


def parse_args(argv, profile):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path, nargs="?")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--detect", action="store_true", help="List the current USB mode")
    modes.add_argument("--inspect", action="store_true", help="Inspect LDROM and return to APROM")
    modes.add_argument("--enter-bootloader", action="store_true")
    modes.add_argument("--exit-bootloader", action="store_true")
    modes.add_argument("--flash", action="store_true", help=f"Program the verified {profile.name} image")
    parser.add_argument("--stay-in-bootloader", action="store_true", help="Keep LDROM active after inspection")
    parser.add_argument("--bootloader-only", action="store_true", help="Require an existing LDROM connection")
    parser.add_argument("--confirm", help=f"Required with --flash: {profile.confirmation}")
    args = parser.parse_args(argv)

    if args.stay_in_bootloader and not args.inspect:
        parser.error("--stay-in-bootloader requires --inspect")
    if args.bootloader_only and not (args.inspect or args.flash):
        parser.error("--bootloader-only requires --inspect or --flash")
    device_only = args.detect or args.inspect or args.enter_bootloader or args.exit_bootloader
    if device_only and args.firmware:
        parser.error("This operation does not take a firmware path")
    if not device_only and args.firmware is None:
        parser.error("Firmware path required for a dry run or programming")
    if args.flash and args.confirm != profile.confirmation:
        parser.error(f"--flash requires --confirm {profile.confirmation}")
    if args.confirm is not None and not args.flash:
        parser.error("--confirm requires --flash")
    return args


def open_ldrom(bootloader_only):
    boot = hid.find_device(hid.LDROM_PID)
    app = hid.find_device(hid.APROM_PID)
    if boot and app:
        raise RuntimeError("APROM and LDROM are both present. Disconnect other Ducky keyboards.")
    if not boot and not bootloader_only:
        path, fd = hid.wait_device(hid.APROM_PID)
        try:
            hid.enter_ldrom(path, fd)
        finally:
            os.close(fd)
    return hid.wait_device(hid.LDROM_PID)


def run_device_operation(args, profile, packets):
    if args.detect:
        for mode, pid in (("APROM", hid.APROM_PID), ("LDROM", hid.LDROM_PID)):
            print(f"{mode} 3233:{pid:04x}: {hid.find_device(pid) or 'not detected'}")
        return

    phase = "Acquiring LDROM"
    fd = None
    try:
        if args.exit_bootloader:
            phase = "Returning to APROM"
            if hid.find_device(hid.APROM_PID):
                raise RuntimeError("An APROM device is already present. Disconnect other Ducky keyboards.")
            path, fd = hid.wait_device(hid.LDROM_PID)
        else:
            path, fd = open_ldrom(args.bootloader_only)
        print(f"LDROM ready: {path}")
        if args.enter_bootloader:
            return

        if not args.exit_bootloader:
            phase = "Inspecting LDROM"
            identity = hid.inspect_ldrom(fd)
            if args.stay_in_bootloader:
                print("Device remains in LDROM.")
                return
            if args.flash:
                phase = "Before programming"
                if identity != profile.identity:
                    raise RuntimeError(f"Device identity/configuration does not match the {profile.name} profile")
                hid.sync(fd)
                print("Starting APROM programming. Keep the keyboard connected.", flush=True)
                for index, packet in enumerate(packets):
                    try:
                        hid.write_report(fd, packet)
                    except (hid.ShortHIDWrite, KeyboardInterrupt):
                        phase = "Programming started"
                        raise
                    phase = "Programming started"
                    reply = hid.read_reply(fd, f"programming packet {index + 1}", timeout=5)
                    hid.check_seq(reply, 4 + 2 * index)
                    if (index + 1) % 50 == 0 or index + 1 == len(packets):
                        print(f"ACK {index + 1}/{len(packets)}", flush=True)
                print("All packet acknowledgments received. Flash contents were not read back.")

        phase = "Returning to APROM"
        hid.send(fd, 0xAB, expect_reply=False)
        os.close(fd)
        fd = None
        path, app_fd = hid.wait_device(hid.APROM_PID, seconds=15)
        os.close(app_fd)
        print(f"APROM detected: {path}")
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt) as exc:
        if phase == "Programming started":
            raise RuntimeError(
                f"{phase}: {exc or 'interrupted'}. Flash may be incomplete. APROM boot was not requested."
            ) from exc
        detail = " No programming commands were sent." if phase != "Returning to APROM" or not args.flash else ""
        raise RuntimeError(f"{phase}: {exc or 'interrupted'}.{detail}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def main(argv=None, profile=STOCK):
    args = parse_args(argv, profile)
    packets = None
    try:
        if args.firmware:
            firmware = args.firmware.read_bytes()
            digest = verify_image(firmware, profile)
            packets = build_packets(firmware)
            print(f"Firmware: {args.firmware} ({profile.name})\nSHA256: {digest}")
            print(f"Size: {len(firmware)} bytes; programming packets: {len(packets)}")
            if not args.flash:
                print(f"Dry run. To program, use --flash --confirm {profile.confirmation}.")
                return
        run_device_operation(args, profile, packets)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Error: {exc}") from exc


def inspect_main():
    main(["--inspect", *sys.argv[1:]])


if __name__ == "__main__":
    main()
