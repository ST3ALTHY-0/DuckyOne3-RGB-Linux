#!/usr/bin/env python3
"""Construct custom Ducky RGB HID report. Dry-run by default; explicit --send required."""
import argparse
import os
from pathlib import Path

from recovery import inspect_ducky_ldrom as hid

p = argparse.ArgumentParser()
p.add_argument('--device', help='Require discovery to match this /dev/hidrawN path')
p.add_argument('--bank', type=int, required=True)
p.add_argument('--index', type=int, required=True)
p.add_argument('--red', type=int, required=True)
p.add_argument('--green', type=int, required=True)
p.add_argument('--blue', type=int, required=True)
p.add_argument('--send', action='store_true', help='Send the report to the detected APROM interface')
a = p.parse_args()
if not 0 <= a.bank < 5 or not 0 <= a.index < 15:
    p.error('bank must be 0..4 and index 0..14')
if any(not 0 <= x <= 255 for x in (a.red, a.green, a.blue)):
    p.error('RGB values must be 0..255')
report = bytearray(64)
report[1] = 0x3a
report[4] = 1
report[5] = 2
report[6:11] = bytes([a.bank, a.index, a.red, a.green, a.blue])
print('64-byte packet:', report.hex(' '))
if a.send:
    try:
        device = hid.find_device(hid.APROM_PID)
        if not device:
            raise RuntimeError('No matching APROM HID interface')
        if a.device and Path(a.device).resolve() != Path(device):
            raise RuntimeError(f'Expected {a.device}, but detected {device}')
        fd = os.open(device, os.O_WRONLY)
        try:
            hid.write_report(fd, report)
        finally:
            os.close(fd)
    except (OSError, RuntimeError) as exc:
        p.error(str(exc))
    print(f'Report written to {device}.')
else:
    print('Dry run: nothing sent. Use --send with the modified V3 firmware.')
