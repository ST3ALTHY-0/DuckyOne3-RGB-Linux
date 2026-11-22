
    
  
#!/usr/bin/env python3
"""Ducky One 3 SF: read-only LDROM identification, then return to APROM."""
import glob
import os
import select
import struct
import time
import subprocess

APROM_DESCRIPTOR = bytes.fromhex(
    '05 01 09 00 a1 01 15 00 25 ff 19 00 29 ff '
    '95 40 75 08 81 02 19 00 29 ff 91 02 c0'
)

def find_device(pid):
    for sysdev in glob.glob(f'/sys/bus/hid/devices/*3233:{pid:04X}*'):
        raws = glob.glob(sysdev + '/hidraw/hidraw*')
        if not raws:
            continue
        if pid == 0x5311:
            with open(sysdev + '/report_descriptor', 'rb') as f:
                if f.read() != APROM_DESCRIPTOR:
                    continue
        return '/dev/' + os.path.basename(raws[0])
    return None

def wait_device(pid, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        path = find_device(pid)
        if path:
            try:
                return path, os.open(path, os.O_RDWR | os.O_NONBLOCK)
            except (PermissionError, FileNotFoundError, OSError):
                pass
        time.sleep(.2)
    raise RuntimeError(f'Could not open {pid:04X} HID interface within {seconds}s')

def send(fd, command, data=b'', expect_reply=True, timeout=3):
    payload = bytearray(64)
    payload[0] = command
    payload[8:8 + len(data)] = data
    # First byte is Linux hidraw Report ID, not part of the 64-byte USB report.
    n = os.write(fd, b'\x00' + payload)
    if n != 65:
        raise RuntimeError(f'Short HID write: {n}')
    if not expect_reply:
        return None
    if not select.select([fd], [], [], timeout)[0]:
        raise TimeoutError(f'No response to 0x{command:02X}')
    reply = os.read(fd, 64)
    if len(reply) != 64:
        raise RuntimeError(f'Short HID response: {len(reply)} bytes')
    print(f'0x{command:02X} response: {reply.hex(" ")}', flush=True)
    return reply

def check_seq(reply, expected):
    seq = struct.unpack_from('<I', reply, 4)[0]
    if seq != expected:
        raise RuntimeError(f'Unexpected packet number {seq}, expected {expected}')
    return seq + 1

def main():
    app_path, app_fd = wait_device(0x5311)
    print('APROM interface:', app_path, flush=True)
    entered_ldrom = False
    boot_fd = None
    try:
        send(app_fd, 0xCC, expect_reply=False)
        entered_ldrom = True
        print('Requested LDROM...', flush=True)
    finally:
        os.close(app_fd)

    try:
        boot_path, boot_fd = wait_device(0x5310)
        print('LDROM interface:', boot_path, flush=True)
        check_seq(send(boot_fd, 0xAE), 2)
        # Sync explicitly resets the updater's counter to 1.
        check_seq(send(boot_fd, 0xA4, struct.pack('<I', 1)), 2)
        version_reply = send(boot_fd, 0xA6)
        check_seq(version_reply, 4)
        print(f'LDROM firmware version: 0x{version_reply[8]:02X}', flush=True)
        id_reply = send(boot_fd, 0xB1)
        check_seq(id_reply, 6)
        print(f'MCU product ID: 0x{struct.unpack_from("<I", id_reply, 8)[0]:08X}', flush=True)
        cfg_reply = send(boot_fd, 0xA2)
        check_seq(cfg_reply, 8)
        print(f'CONFIG0: 0x{struct.unpack_from("<I", cfg_reply, 8)[0]:08X}', flush=True)
        print(f'CONFIG1: 0x{struct.unpack_from("<I", cfg_reply, 12)[0]:08X}', flush=True)
    finally:
        if boot_fd is not None:
            try:
                print('Requesting return to APROM...', flush=True)
                send(boot_fd, 0xAB, expect_reply=False)
            except OSError as e:
                print('Could not send APROM command:', e, flush=True)
            finally:
                os.close(boot_fd)
        time.sleep(2)
        subprocess.run(['lsusb', '-d', '3233:'], check=False)

if __name__ == '__main__':
    main()

