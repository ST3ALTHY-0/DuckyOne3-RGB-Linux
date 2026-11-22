
    
  
#!/usr/bin/env python3
"""Ducky One 3 SF Nuvoton LDROM flasher. Dry-run by default.

Use only with the exact firmware/MCU verified during reverse engineering.
"""
import argparse
import hashlib
import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_ducky_ldrom import wait_device, send, check_seq

EXPECTED_SHA = '78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258'
EXPECTED_PID = 0x01205212
EXPECTED_CONFIG0 = 0xF7FFFF7C
EXPECTED_CONFIG1 = 0x00032800
EXPECTED_LDROM = 0x33


def write_report(fd, payload, label):
    if len(payload) != 64:
        raise ValueError(f'{label}: expected 64-byte payload')
    written = os.write(fd, b'\x00' + payload)
    if written != 65:
        raise OSError(f'{label}: short HID write: {written}')


def transfer(fd, payload, label, expected_sequence):
    import select
    write_report(fd, payload, label)
    if not select.select([fd], [], [], 5)[0]:
        raise TimeoutError(f'{label}: no acknowledgment; flash state is uncertain')
    response = os.read(fd, 64)
    if len(response) != 64:
        raise RuntimeError(f'{label}: short acknowledgment: {len(response)}')
    check_seq(response, expected_sequence)
    # Packet sequencing is not proof that flash programming succeeded.
    return response


def build_packets(fw):
    first = bytearray(64)
    first[0] = 0xA0
    struct.pack_into('<I', first, 12, len(fw))
    first[16:64] = fw[:48]
    packets = [bytes(first)]
    for pos in range(48, len(fw), 56):
        packet = bytearray(64)
        part = fw[pos:pos+56]
        packet[8:8+len(part)] = part
        packets.append(bytes(packet))
    return packets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    parser.add_argument('--flash', action='store_true', help='Perform destructive APROM programming')
    parser.add_argument('--confirm', default='', help='Must equal FLASH-DUCKY-V3')
    args = parser.parse_args()
    fw = args.firmware.read_bytes()
    digest = hashlib.sha256(fw).hexdigest()
    if digest != EXPECTED_SHA or len(fw) != 43084:
        parser.error('Firmware does not match the validated V3 image')
    packets = build_packets(fw)
    print(f'Firmware: {args.firmware}\nSHA256: {digest}\nSize: {len(fw)} bytes')
    print(f'Flash packets: {len(packets)}; first payload: 48 bytes; continuation: 56 bytes')
    print(f'First packet length field: {packets[0][12:16].hex(" ")}')
    print(f'Last packet payload: {(len(fw)-48)%56 or 56} firmware bytes')
    if not args.flash:
        print('DRY RUN: No USB commands sent. Use --flash --confirm FLASH-DUCKY-V3 to program.')
        return
    if args.confirm != 'FLASH-DUCKY-V3':
        parser.error('Explicit confirmation required: --confirm FLASH-DUCKY-V3')

    boot_fd = None
    flashed = False
    try:
        boot_path = None
        try:
            boot_path, boot_fd = wait_device(0x5310, seconds=1)
            print(f'Already in LDROM: {boot_path}', flush=True)
        except RuntimeError:
            app_path, app_fd = wait_device(0x5311)
            try:
                print(f'APROM: {app_path}; entering LDROM', flush=True)
                send(app_fd, 0xCC, expect_reply=False)
            finally:
                os.close(app_fd)
            boot_path, boot_fd = wait_device(0x5310)
            print(f'LDROM: {boot_path}', flush=True)

        check_seq(send(boot_fd, 0xAE), 2)
        check_seq(send(boot_fd, 0xA4, struct.pack('<I', 1)), 2)
        version = send(boot_fd, 0xA6)
        check_seq(version, 4)
        ident = send(boot_fd, 0xB1)
        check_seq(ident, 6)
        config = send(boot_fd, 0xA2)
        check_seq(config, 8)
        pid = struct.unpack_from('<I', ident, 8)[0]
        cfg0, cfg1 = struct.unpack_from('<II', config, 8)
        print(f'LDROM version={version[8]:02X}; MCU={pid:08X}; CONFIG={cfg0:08X}/{cfg1:08X}')
        if (version[8], pid, cfg0, cfg1) != (EXPECTED_LDROM, EXPECTED_PID, EXPECTED_CONFIG0, EXPECTED_CONFIG1):
            raise RuntimeError('Device identity/config differs from verified keyboard; aborting')
        check_seq(send(boot_fd, 0xA4, struct.pack('<I', 1)), 2)
        print('Starting destructive flash; do not disconnect the keyboard.', flush=True)
        # The update sync returns 2; the first 0xA0 response returns 4, then 6, 8, ...
        for i, packet in enumerate(packets):
            expected = 4 + 2*i
            transfer(boot_fd, packet, f'flash packet {i+1}/{len(packets)}', expected)
            flashed = True
            if (i+1) % 50 == 0 or i+1 == len(packets):
                print(f'ACK {i+1}/{len(packets)}', flush=True)
        print('All packet sequence acknowledgments received. Requesting APROM boot.', flush=True)
        send(boot_fd, 0xAB, expect_reply=False)
    except Exception:
        print('ERROR: Flash state may be incomplete. Do not assume firmware is valid.', file=sys.stderr)
        raise
    finally:
        if boot_fd is not None:
            os.close(boot_fd)
    time.sleep(2)
    print('Flash transfer completed. Verify keyboard USB enumeration and functionality.')

if __name__ == '__main__':
    main()

