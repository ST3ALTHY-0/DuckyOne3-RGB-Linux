#!/usr/bin/env python3
"""Construct custom Ducky RGB HID report. Dry-run by default; explicit --send required."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--device', help='Explicit /dev/hidrawN device (required with --send)')
p.add_argument('--bank', type=int, required=True)
p.add_argument('--index', type=int, required=True)
p.add_argument('--red', type=int, required=True)
p.add_argument('--green', type=int, required=True)
p.add_argument('--blue', type=int, required=True)
p.add_argument('--send', action='store_true', help='Write 64-byte report to the specified HID interface')
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
    if not a.device or not a.device.startswith('/dev/hidraw'):
        p.error('--send requires an explicit --device /dev/hidrawN')
    with open(Path(a.device), 'wb', buffering=0) as f:
        f.write(b'\x00' + report)
    print('Report written (device behavior not verified).')
else:
    print('Dry run: nothing sent. Use --send only after confirming the HID interface and firmware protocol.')
