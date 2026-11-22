
#!/usr/bin/env python3
import argparse
import hashlib
import struct
from pathlib import Path

EXPECTED_SHA256 = (
    "966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844"
)

SOURCE_OFFSET = 0xA54E
COMPRESSED_SIZE = 0x270
MAPPING_OFFSET = 0x2E0
MAPPING_SIZE = 16

parser = argparse.ArgumentParser(description="Extract LED mappings from original Ducky firmware.")
parser.add_argument("--firmware", type=Path, required=True, help="Path to the original firmware binary")
args = parser.parse_args()

firmware = args.firmware.read_bytes()

actual_hash = hashlib.sha256(firmware).hexdigest()
if actual_hash != EXPECTED_SHA256:
    raise SystemExit(
        f"Unexpected firmware SHA256: {actual_hash}\n"
        "Use the original, unmodified firmware."
    )

compressed = firmware[
    SOURCE_OFFSET:SOURCE_OFFSET + COMPRESSED_SIZE
]

if len(compressed) != COMPRESSED_SIZE:
    raise SystemExit("Firmware does not contain the complete compressed stream")

output = bytearray()
pos = 0

def read_byte():
    global pos
    if pos >= len(compressed):
        raise ValueError("Unexpected end of compressed stream")
    value = compressed[pos]
    pos += 1
    return value

while pos < len(compressed):
    control = read_byte()

    literal_count = control & 0x03

    if literal_count == 0:
        literal_count = read_byte() + 3

    match_count = control >> 4

    if match_count == 15:
        match_count = read_byte() + 15

    # The firmware's decoder copies literal_count - 1 bytes.
    for _ in range(literal_count - 1):
        output.append(read_byte())

    if match_count:
        offset_low = read_byte()
        offset_high = (control >> 2) & 0x03

        if offset_high == 3:
            offset_high = read_byte()

        distance = offset_low + offset_high * 256

        if distance == 0 or distance > len(output):
            raise ValueError(
                f"Invalid back-reference at input 0x{pos:X}: "
                f"distance={distance}, output_size={len(output)}"
            )

        # The firmware copies match_count + 2 bytes.
        for _ in range(match_count + 2):
            output.append(output[-distance])

print(f"Compressed bytes: {len(compressed)}")
print(f"Decompressed bytes: {len(output)}")

if len(output) < MAPPING_OFFSET + MAPPING_SIZE:
    raise SystemExit("Decompressed data does not reach the mapping table")

mapping = output[MAPPING_OFFSET:MAPPING_OFFSET + MAPPING_SIZE]

print(f"\nLED mapping bytes: {mapping.hex(' ')}")
print("\nLED mappings:")

for i in range(4):
    original, mapped = struct.unpack_from("<HH", mapping, i * 4)

    print(
        f"Entry {i}: "
        f"0x{original:04X} "
        f"(bank {original >> 8}, index {original & 0xFF}) "
        f"<-> "
        f"0x{mapped:04X} "
        f"(bank {mapped >> 8}, index {mapped & 0xFF})"
    )

Path("startup_sram.bin").write_bytes(output)
print("\nSaved startup_sram.bin")
