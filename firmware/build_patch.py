#!/usr/bin/env python3
"""Build an OFFLINE-only Ducky One 3 SF firmware extension. NEVER flashes."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

HOOK = 0x9646
EXTENSION = 0xA7C0
ORIGINAL_HANDLER = 0x9654
SUPPORTED_FIRMWARE = {
    "1.16": {
        "sha256": "966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844",
    },
}


def verify_firmware(data):
    digest = hashlib.sha256(data).hexdigest()
    for version, info in SUPPORTED_FIRMWARE.items():
        if digest == info["sha256"]:
            print(f"Detected supported firmware V{version}")
            return version
    raise ValueError(
        "Unsupported firmware image. "
        "This patch currently supports only Ducky One 3 SF RGB V1.16."
    )


def encode_bl(source, target):
    delta = target - (source + 4)
    assert delta % 2 == 0 and -(1 << 24) <= delta < (1 << 24)
    s = (delta >> 24) & 1
    i1 = (delta >> 23) & 1
    i2 = (delta >> 22) & 1
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    return struct.pack('<HH', 0xF000 | (s << 10) | ((delta >> 12) & 0x3ff),
                       0xD000 | (j1 << 13) | (j2 << 11) | ((delta >> 1) & 0x7ff))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('firmware', type=Path, help='Original, unmodified Ducky One 3 SF RGB V1.16 firmware binary')
    parser.add_argument('--output', type=Path, default=Path('ducky_one3_sf_rgb_v1.bin'))
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--objcopy', default='llvm-objcopy')
    args = parser.parse_args()
    original = args.firmware.read_bytes()
    try:
        verify_firmware(original)
    except ValueError as exc:
        parser.error(str(exc))
    assert len(original) == 42942, f'Unexpected firmware length: {len(original)}'
    assert original[HOOK:HOOK+4] == bytes.fromhex('00 f0 05 f8'), 'Original USB hook mismatch'
    with tempfile.TemporaryDirectory() as tmp:
        elf = Path(tmp)/'rgb.elf'
        raw = Path(tmp)/'rgb.bin'
        asm = Path(__file__).with_name('rgb_dispatcher.S')
        subprocess.run([args.clang, '--target=armv6m-none-eabi', '-mthumb', '-nostdlib', '-fuse-ld=lld',
                        '-Wl,--build-id=none', '-Wl,--image-base=0', f'-Wl,-Ttext=0x{EXTENSION:x}', '-Wl,-e,rgb_dispatcher',
                        str(asm), '-o', str(elf)], check=True)
        subprocess.run([args.objcopy, '-O', 'binary', '--only-section=.text', str(elf), str(raw)], check=True)
        payload = raw.read_bytes()
    assert payload.startswith(bytes.fromhex('70 b5')), f'Unexpected dispatcher prologue: {payload[:4].hex()}'
    patched = bytearray(original)
    patched.extend(b'\xff' * (EXTENSION - len(patched)))
    patched.extend(payload)
    patched[HOOK:HOOK+4] = encode_bl(HOOK, EXTENSION)
    assert patched[HOOK:HOOK+4] == bytes.fromhex('01 f0 bb f8')
    assert patched[:HOOK] == original[:HOOK]
    assert patched[HOOK+4:len(original)] == original[HOOK+4:]
    args.output.write_bytes(patched)
    print('Original SHA256:', hashlib.sha256(original).hexdigest())
    print('Dispatcher length:', len(payload), 'bytes')
    print('Extension address:', hex(EXTENSION))
    print('Hook bytes:', patched[HOOK:HOOK+4].hex(' '))
    print('Patched firmware:', args.output)
    print('Patched size:', len(patched))
    print('Patched SHA256:', hashlib.sha256(patched).hexdigest())
    print('OFFLINE ONLY: do not flash until bootloader and recovery are verified.')

if __name__ == '__main__':
    main()
