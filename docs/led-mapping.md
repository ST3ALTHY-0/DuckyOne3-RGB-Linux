# LED Mapping — Ducky One 3 SF RGB


## Overview

This document describes the LED addressing system used by the **Ducky One 3 SF RGB** keyboard and the work required to map its RGB lighting to physical keys.

The project's custom firmware allows software to change individual LED colors by specifying a logical row and column.

Initial testing identified a **5-row × 15-column logical grid**, providing 75 addressable positions.

However, these positions do not necessarily correspond one-to-one with physical keys.

For example, larger keys such as the spacebar appear to occupy multiple logical positions.

The ultimate goal is to translate these logical addresses into meaningful key identifiers so users can select and customize individual keys through a graphical application.

## 1. Logical LED Addressing

The V3 firmware accepts two values identifying a logical LED position.

| Field | Valid range | Description |
|---|---|---|
| Bank | `0–4` | Logical row |
| Index | `0–14` | Logical column |

The logical grid contains 75 address combinations.

### Grid Representation

```text
                 Logical Column
         00 01 02 03 04 05 06 07 08 09 10 11 12 13 14

Bank 0   [] [] [] [] [] [] [] [] [] [] [] [] [] [] []
Bank 1   [] [] [] [] [] [] [] [] [] [] [] [] [] [] []
Bank 2   [] [] [] [] [] [] [] [] [] [] [] [] [] [] []
Bank 3   [] [] [] [] [] [] [] [] [] [] [] [] [] [] []
Bank 4   [] [] [] [] [] [] [] [] [] [] [] [] [] [] []
```

Testing suggests that banks generally correspond to the physical rows of the keyboard, while indices represent horizontal positions.

The exact correspondence between grid positions and keycaps has not yet been documented.

### Internal LED Identifier

The firmware represents a logical LED address using a 16-bit identifier:

```c
uint16_t led_id = (bank << 8) | index;
```

Examples:

| Bank | Index | LED identifier |
|---|---|---|
| 0 | 0 | `0x0000` |
| 0 | 5 | `0x0005` |
| 1 | 0 | `0x0100` |
| 2 | 7 | `0x0207` |
| 3 | 10 | `0x030A` |
| 4 | 14 | `0x040E` |

The identifier is passed through the firmware's internal LED mapping functionality before the RGB color is written.

## 2. Observed Physical Mapping

A sequential test sent RGB commands to every logical address.

The test iterated through banks `0–4` and indices `0–14`, setting each address to red.

### Confirmed Observations

- Commands successfully caused keys throughout the keyboard to flash red.
- Banks generally correspond to physical keyboard rows.
- Indices generally progress horizontally across a row.
- Some logical addresses appear to correspond to the same physical key.
- Larger keys, including the spacebar, appear to occupy multiple logical positions.
- The keyboard's onboard lighting engine quickly restores the original lighting color.

### Larger Keys

During testing, the spacebar appeared to correspond to approximately five or six logical indices.

This may indicate that the logical addressing system represents the physical width of a key rather than assigning exactly one address per key.

Alternatively, multiple logical addresses may resolve to the same internal LED.

The exact explanation remains unverified.

**Important:** The existence of 75 logical addresses does not establish that the keyboard has 75 independently controllable physical LEDs.

## 3. Physical Keyboard Layout

The Ducky One 3 SF uses a compact 65% keyboard layout.

The following diagram is a simplified representation of the general key arrangement, not a verified LED-address map.

```text
┌──────────────────────────────────────────────────────────────┐
│ Esc  1  2  3  4  5  6  7  8  9  0  -  =   Backspace          │
│ Tab   Q  W  E  R  T  Y  U  I  O  P  [  ]   \                │
│ Caps   A  S  D  F  G  H  J  K  L  ;  '   Enter             │
│ Shift    Z  X  C  V  B  N  M  ,  .  /    Shift      ↑       │
│ Ctrl Win Alt       Space       Alt Fn Ctrl       ←  ↓  →    │
└──────────────────────────────────────────────────────────────┘
```

The exact key arrangement varies by keyboard layout and revision.

The diagram is intended only as a visual reference for future mapping work.

No specific logical LED addresses have yet been assigned to the illustrated key names.

## 4. Firmware LED Mapping Function

The original firmware contains an internal function that translates logical LED identifiers into physical or internal LED positions.

The identified mapping function has its Thumb entry point at:

```text
0x00004BE3
```

The V3 custom RGB dispatcher invokes this existing function.

### Mapping Data

Firmware analysis identified compressed mapping data and a corresponding decompressed SRAM region.

| Property | Address |
|---|---|
| Compressed mapping data | `0x0000A54E` |
| Decompressed mapping data | `0x200002E0` |
| Mapping function | `0x00004BE3` |

The mapping data is decompressed during firmware initialization.

The current analysis suggests that the mapping function uses this data to translate logical addresses into internal positions.

The exact structure of the mapping table remains to be fully documented.

### Why the Mapping Matters

The keyboard's logical LED addresses are not necessarily equivalent to physical LED indices.

For example:

```text
Logical address
    |
    v
Bank / Index
    |
    v
Firmware mapping function
    |
    v
Internal LED position
    |
    v
RGB buffer
    |
    v
Physical LED
```

A software configuration application will need to understand this mapping to reliably associate key names with RGB addresses.

## 5. RGB Buffer Organization

The firmware's RGB buffer begins at:

```text
0x20001770
```

Each entry contains three 16-bit color channels:

```text
Red:   2 bytes
Green: 2 bytes
Blue:  2 bytes
----------------
Total: 6 bytes
```

The identified address calculation is:

```c
address = 0x20001770 + (bank * 0x5A) + (index * 6);
```

Since `0x5A` equals 90 bytes:

```text
15 entries × 6 bytes = 90 bytes per bank
```

The complete five-bank logical buffer therefore occupies 450 bytes.

This calculation describes the identified internal RGB storage layout. It should not be interpreted as proof that every logical position corresponds to a unique physical LED.

## 6. Custom RGB Command

The V3 firmware introduces a USB HID command for setting an individual logical LED color.

### Packet Structure

| Offset | Description |
|---|---|
| `0` | `0x00` |
| `1` | `0x3A` |
| `2–3` | `0x00` |
| `4` | `0x01` |
| `5` | `0x02` |
| `6` | Bank |
| `7` | Index |
| `8` | Red |
| `9` | Green |
| `10` | Blue |
| `11–63` | Reserved |

Example:

```text
00 3A 00 00 01 02 02 07 FF 00 00 ...
```

This requests that logical address `(2, 7)` be set to red.

The payload is 64 bytes. Some host HID interfaces require an additional leading report-ID byte.

For more information, see [hid-protocol.md](hid-protocol.md).

## 7. Testing Logical LED Addresses

The following Python script sequentially sends a red RGB command to every logical address.

It can be used to observe the relationship between logical addresses and physical keys.

```python
import time

DEVICE = "/dev/hidraw6"

with open(DEVICE, "wb", buffering=0) as device:
    for bank in range(5):
        for index in range(15):
            print(f"Testing bank={bank}, index={index}")

            report = bytearray(64)

            report[1] = 0x3A
            report[4] = 0x01
            report[5] = 0x02

            report[6] = bank
            report[7] = index

            report[8] = 255
            report[9] = 0
            report[10] = 0

            written = device.write(b"\x00" + report)

            if written != 65:
                raise IOError(
                    f"Incomplete HID write: {written}"
                )

            time.sleep(0.5)
```

Replace `/dev/hidraw6` with the correct vendor-defined HID interface.

### Testing Limitations

The current V3 firmware does not preserve externally assigned colors.

Consequently, LEDs may only flash briefly before returning to the onboard lighting mode.

Increasing the delay between commands makes it easier to identify which address is being tested, but does not extend the duration of the flash itself.

A persistent RGB mode will make this mapping process significantly easier.

## 8. Recording the Physical Mapping

The next step is to associate every logical address with the physical key or LED it affects.

A recommended recording format is:

| Bank | Index | Physical key | Verified | Notes |
|---|---|---|---|---|
| 0 | 0 | Unknown | No | |
| 0 | 1 | Unknown | No | |
| 0 | 2 | Unknown | No | |
| 0 | 3 | Unknown | No | |
| 0 | 4 | Unknown | No | |
| ... | ... | ... | ... | ... |
| 4 | 14 | Unknown | No | |

Avoid assigning physical key names based solely on their expected position in the keyboard layout.

Each mapping should be confirmed through hardware testing or reliable firmware analysis.

### Suggested CSV Format

A machine-readable mapping file could use the following columns:

```csv
bank,index,key_name,verified,notes
0,0,,false,
0,1,,false,
0,2,,false,
0,3,,false,
0,4,,false,
```

Once verified, this data can be used to construct a physical-key mapping in the software controller.

## 9. Handling Duplicate Addresses

Some logical addresses may affect the same physical LED.

For example, suppose testing eventually establishes that three logical positions all control the same LED:

```text
Bank 4, Index 4 ──┐
                  ├──> Same physical LED
Bank 4, Index 5 ──┤
                  │
Bank 4, Index 6 ──┘
```

This is a hypothetical example, not a confirmed mapping.

In such cases, the software should avoid treating these addresses as independent lighting zones.

A possible mapping representation would be:

```json
{
  "key": "SPACE",
  "logical_addresses": [
    [4, 4],
    [4, 5],
    [4, 6]
  ],
  "verified": false
}
```

The values above are illustrative only.

Once the mapping is verified, software could choose one canonical address per independently controllable LED while retaining information about aliases.

## 10. Proposed Software Mapping Format

A future keyboard controller should use a hardware-specific mapping file.

A possible structure is:

```json
{
  "keyboard": "Ducky One 3 SF RGB",
  "mapping_version": 1,
  "grid": {
    "banks": 5,
    "indices_per_bank": 15
  },
  "keys": {
    "ESC": {
      "addresses": [],
      "verified": false
    },
    "A": {
      "addresses": [],
      "verified": false
    },
    "SPACE": {
      "addresses": [],
      "verified": false
    }
  }
}
```

Addresses are intentionally left empty because the exact mapping has not yet been established.

The final format may include additional fields such as:

- Physical key position.
- Key width and height.
- Logical address aliases.
- Independent LED identifiers.
- Keyboard layout variant.
- Hardware revision.
- Firmware compatibility.

This would allow the graphical application to display a physical keyboard layout while translating user selections into the appropriate HID commands.

## 11. Planned Mapping Tools

A dedicated LED mapping utility would make testing more efficient.

Potential features include:

### Interactive Address Tester

Allow users to select a bank and index and send an RGB command.

For example:

```text
Bank:  [ 2 ]
Index: [ 7 ]

Color: Red

[ Send RGB Command ]
```

### Sequential LED Scanner

Automatically cycle through all 75 logical addresses.

The utility could display the current address while the user records the physical key that flashes.

### Visual Keyboard Mapper

Display a keyboard layout and allow the user to click the corresponding physical key after each test.

The software would then associate the selected key with the current logical address.

### Duplicate Detection

Once persistent RGB control is available, the software could help identify addresses that affect the same LED.

Automated duplicate detection may require additional firmware support or visual observation, since the current HID protocol does not provide physical LED feedback.

## 12. Known Limitations

The current mapping research has several limitations:

- The complete physical-key mapping is not yet known.
- Some logical addresses may be aliases.
- The exact mapping behavior of larger keys remains unverified.
- The logical grid may contain unused or duplicated positions.
- Custom colors are not persistent in V3.
- Only one keyboard model has been tested.
- Different keyboard layouts may require different mapping files.
- The internal mapping table has not been fully decoded.

These limitations should be resolved through additional firmware analysis and physical testing.

## 13. Next Steps

The immediate mapping goals are:

1. Implement persistent software-controlled RGB lighting.
2. Develop an interactive LED address tester.
3. Record all 75 logical address results.
4. Identify unused or duplicate addresses.
5. Associate verified addresses with physical key names.
6. Create a machine-readable mapping file.
7. Integrate the mapping into the graphical keyboard configuration application.

A verified physical-key mapping is essential for providing intuitive per-key RGB customization.

Rather than requiring users to enter numerical LED addresses, the final software should allow them to select keys directly.

---

## Related Documentation

- [README.md](../README.md) — Project overview and development status.
- [firmware.md](firmware.md) — Firmware architecture, patching, and reverse-engineering findings.
- [hid-protocol.md](hid-protocol.md) — USB HID communication and custom RGB commands.

## Disclaimer

This document describes experimental reverse-engineering findings for the Ducky One 3 SF RGB.

The mapping is incomplete and may change as additional information becomes available.

The project is independent and is not affiliated with or endorsed by Ducky or Nuvoton.