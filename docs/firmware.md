# Firmware Architecture & Reverse Engineering

> **AI-Assisted Development:** Firmware analysis, ARM assembly patching, protocol investigation, and debugging were performed with significant assistance AI tools. Findings were developed through reverse engineering and testing on physical hardware. Some internal function names and interpretations are provisional.

## Overview

This document describes the firmware reverse-engineering work performed on the **Ducky One 3 SF RGB** keyboard.

The objective is to enable external software to control the keyboard's RGB lighting and, eventually, other configurable features without requiring physical keyboard shortcuts.

The current V3 firmware patch introduces a custom USB HID command handler that can update individual LED colors using the keyboard's existing RGB functionality.

The patch has been successfully flashed and tested on physical hardware.

**Current limitation:** Custom RGB colors are displayed briefly before the keyboard's original lighting engine restores its configured colors.

## 1. Hardware Information

| Property | Value |
|---|---|
| Keyboard | Ducky One 3 SF RGB |
| Microcontroller | Nuvoton NUC1261SG4AE |
| Architecture | ARM Cortex-M0 |
| Application firmware | APROM |
| Bootloader firmware | LDROM |
| Application USB VID:PID | `3233:5311` |
| Bootloader USB VID:PID | `3233:5310` |
| Bootloader version | `0x33` |
| MCU product ID | `0x01205212` |
| CONFIG0 | `0xF7FFFF7C` |
| CONFIG1 | `0x00032800` |

The microcontroller contains 256 KiB of application flash memory.

The keyboard uses separate application and bootloader execution environments.

### APROM

APROM contains the keyboard's main application firmware, including:

- Keyboard input processing.
- USB HID communication.
- RGB lighting control.
- Keyboard configuration handling.
- Internal LED mapping and rendering.

The keyboard normally enumerates as:

```text
3233:5311
```

### LDROM

LDROM contains the bootloader used for firmware updates.

The keyboard enumerates as:

```text
3233:5310
```

The bootloader supports commands for device identification, configuration inspection, firmware programming, and returning to application mode.

The V3 patch modifies APROM only. It does not intentionally modify LDROM or the MCU configuration words.

## 2. Original Firmware Image

The original application firmware was extracted from an official Ducky firmware updater.

The updater contains the firmware image as an embedded byte array.

### Original Image

| Property | Value |
|---|---|
| Filename | `ducky_one3_sf_firmware.bin` |
| Size | 42,942 bytes |
| Hexadecimal size | `0xA7BE` |
| Format | Raw ARM application firmware |

SHA-256:

```text
966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844
```

The firmware was analyzed to identify the USB command handling, RGB buffer management, LED address mapping, and lighting refresh mechanisms.

The project does not redistribute the original proprietary firmware image.

### Firmware Compatibility

The V3 patch depends on specific function addresses within the extracted firmware image.

Consequently, it must not be applied to an arbitrary firmware version.

Future versions should implement strict input-image hash validation to prevent patching incompatible firmware.

## 3. Relevant Firmware Functions

The following functions and memory locations were identified during reverse engineering.

Function names beginning with `FUN_` are analysis-generated names rather than official vendor symbols.

### USB Command Handling

| Address | Function | Purpose |
|---|---|---|
| `0x963C` | `FUN_0000963C` | USB command processing wrapper |
| `0x9654` | `FUN_00009654` | Original command handler |
| `0x9F0E` | `FUN_00009F0E` | USB response transmission |
| `0x9F26` | `FUN_00009F26` | USB report reception |

The USB processing wrapper checks whether a command is ready and then calls the original command handler.

The V3 patch modifies this call so that incoming reports first pass through a custom dispatcher.

### RGB Functions

| Address | Function | Purpose |
|---|---|---|
| `0x3160` | `FUN_00003160` | RGB value writer |
| `0x321C` | `FUN_0000321C` | Lighting refresh processing |
| `0x3B08` | `FUN_00003B08` | Lighting rendering routine |
| `0x4BE2` | Logical LED mapping function | Maps logical LED addresses to internal positions |

The RGB writer accepts a logical LED identifier and three color values.

The logical LED identifier is encoded as:

```text
(bank << 8) | index
```

The RGB color values are passed as 16-bit integers.

The custom dispatcher converts incoming 8-bit values into 16-bit values by multiplying each channel by 257:

```text
R16 = R8 * 257
G16 = G8 * 257
B16 = B8 * 257
```

This maps:

```text
0   -> 0x0000
255 -> 0xFFFF
```

### Important SRAM Addresses

| Address | Purpose |
|---|---|
| `0x2000254C` | USB receive report buffer |
| `0x2000258C` | USB transmit report buffer |
| `0x2000269F` | USB command-ready flag |
| `0x20001770` | RGB color buffer |
| `0x200027B0` | Lighting refresh flag |
| `0x20000E18` | Lighting framebuffer region |
| `0x200002E0` | Decompressed LED mapping data |

These addresses were identified for the tested firmware image and must not be assumed valid for other firmware revisions.

## 4. RGB Buffer Organization

The original firmware maintains RGB values in SRAM.

The identified RGB buffer begins at:

```text
0x20001770
```

Each logical LED entry occupies six bytes, corresponding to three 16-bit color channels.

The observed address calculation is:

```text
address = 0x20001770 + (bank * 0x5A) + (index * 6)
```

Where:

- `bank` is the logical LED row.
- `index` is the logical LED column.
- `0x5A` is 90 bytes, corresponding to 15 entries of six bytes each.

This supports a logical grid of five rows and fifteen columns.

### Logical LED Mapping

The firmware also contains a mapping routine that translates logical LED identifiers into internal LED positions.

The mapping data is decompressed into SRAM during initialization.

Identified locations:

```text
Compressed mapping data: 0xA54E
Decompressed mapping:   0x200002E0
```

The mapping routine must be considered when addressing LEDs, since the physical keyboard layout is not necessarily a direct one-to-one representation of the logical grid.

Initial testing indicates that some larger physical keys correspond to multiple logical addresses.

A complete physical-key mapping remains to be documented.

## 5. USB HID Communication

The application firmware exposes a vendor-defined USB HID interface supporting 64-byte reports.

The custom RGB protocol uses this interface.

### Application Interface

USB identifier:

```text
VID: 0x3233
PID: 0x5311
```

The observed vendor-defined report descriptor is:

```text
06 00 FF 09 01 A1 01 19 01 29 40 15 00
26 FF 00 75 08 95 40 81 00 19 01 29 40
91 00 C0
```

This descriptor provides 64-byte input and output reports.

On Linux, writing to a `hidraw` device requires an additional leading report-ID byte:

```python
device.write(b"\x00" + report)
```

The `report` variable contains the 64-byte HID payload.

### Original Command Handler

The original firmware processes commands using a header that includes `0x3A`.

The identified handler supports existing subcommands, including firmware-related operations.

The custom dispatcher extends this mechanism by recognizing a new RGB command while forwarding other commands to the original handler.

## 6. V3 Firmware Patch

The V3 patch adds a small ARM Thumb assembly routine that intercepts incoming USB commands.

### Patched Image

| Property | Value |
|---|---|
| Filename | `ducky_one3_sf_rgb_v3.bin` |
| Size | 43,084 bytes |
| Hexadecimal size | `0xA84C` |
| Custom dispatcher address | `0xA7C0` |
| Modified call instruction | `0x9646` |
| Dispatcher size | 140 bytes |

SHA-256:

```text
78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258
```

### Hook Implementation

The original USB command-processing wrapper contains a call to the original handler.

At offset `0x9646`, the original instruction is:

```text
00 F0 05 F8
```

This is replaced with:

```text
01 F0 BB F8
```

The modified instruction redirects execution to the custom dispatcher at `0xA7C0`.

The dispatcher forwards unrecognized commands to the original handler at Thumb address `0x9655`.

### Dispatcher Behavior

The custom handler performs the following operations:

1. Saves the registers it uses.
2. Reads the incoming USB HID report.
3. Checks the custom command header.
4. Validates the requested LED address.
5. Calls the original LED mapping function.
6. Converts RGB values from 8-bit to 16-bit.
7. Calls the original RGB-writing function.
8. Sets the lighting refresh flag.
9. Restores registers and returns.

Commands that do not match the custom RGB header are passed to the original firmware handler.

### Custom RGB Packet

The 64-byte payload has the following format:

| Offset | Description |
|---|---|
| `0` | `0x00` |
| `1` | `0x3A` |
| `2–3` | `0x00 0x00` |
| `4` | `0x01` |
| `5` | `0x02` |
| `6` | Bank |
| `7` | Index |
| `8` | Red |
| `9` | Green |
| `10` | Blue |
| `11–63` | Reserved |

Example red command:

```text
00 3A 00 00 01 02 00 00 FF 00 00 ...
```

The dispatcher validates the logical address before invoking the RGB writer.

### Command Processing

```text
Incoming USB Report
        |
        v
Custom Dispatcher
        |
        v
Matches Custom RGB Header?
        |
   +----+----+
   |         |
   No       Yes
   |         |
   v         v
Original   Validate LED Address
Handler      |
             v
          Map LED
             |
             v
        Convert RGB
             |
             v
       Write RGB Values
             |
             v
       Set Refresh Flag
             |
             v
           Return
```

## 7. Building the Patch

The patch source is written in ARM Thumb assembly and assembled for the ARM Cortex-M0 architecture.

The build script modifies the original firmware image and appends the custom dispatcher.

Example:

```bash
python3 build_patch.py \
  ../ducky_one3_sf_firmware.bin \
  --output ducky_one3_sf_rgb_v3.bin
```

The tested build produces a 43,084-byte image.

Verify its SHA-256 checksum before flashing:

```bash
sha256sum ducky_one3_sf_rgb_v3.bin
```

Expected:

```text
78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258
```

A matching output hash verifies that the generated file matches the tested V3 build. It does not independently establish compatibility with another keyboard.

## 8. Nuvoton Bootloader Protocol

The keyboard can enter LDROM from APROM using a USB HID command.

The tested bootloader identifies itself as:

```text
VID:PID 3233:5310
Version 0x33
MCU PID 0x01205212
```

### Identified Commands

| Command | Description |
|---|---|
| `0xCC` | Request LDROM entry from APROM |
| `0xAE` | Connect |
| `0xA4` | Synchronize packet numbering |
| `0xA6` | Read bootloader version |
| `0xB1` | Read MCU product ID |
| `0xA2` | Read configuration |
| `0xA0` | Program APROM |
| `0xAB` | Run APROM |

### Firmware Transfer

The flashing process sends the firmware image in 64-byte HID packets.

The first firmware packet contains:

- APROM update command `0xA0`.
- Firmware image length.
- The first 48 bytes of firmware data.

Subsequent packets carry up to 56 bytes of firmware data each.

The bootloader returns sequence-number acknowledgments.

For the tested V3 image:

```text
Firmware size: 43,084 bytes
Total packets: 770
First payload: 48 bytes
Continuation payload: 56 bytes
```

The bootloader acknowledged all 770 packets during the successful flash test.

After the transfer, the flasher sent `0xAB` to request execution of APROM.

The keyboard subsequently operated normally.

### Verification Limitations

The current flasher validates packet acknowledgment sequences but does not perform a complete readback of programmed flash memory.

Therefore, successful packet acknowledgments should not be interpreted as proof that every byte was programmed correctly.

## 9. Testing Results

### Successful Firmware Flash

The V3 firmware was successfully transferred using the experimental flashing tool.

The following behavior was observed:

- The keyboard entered LDROM.
- The expected MCU and configuration values were reported.
- All 770 firmware packets were acknowledged.
- The bootloader accepted the request to return to APROM.
- The keyboard resumed normal operation.
- The keyboard continued to function as an input device.

### RGB Command Testing

Custom RGB commands were sent through the keyboard's vendor-defined HID interface.

A test iterated over all 75 logical addresses:

```python
for bank in range(5):
    for index in range(15):
        # Send red RGB command
        ...
```

The test caused keys throughout the keyboard to briefly illuminate red.

This confirmed that the modified firmware could receive and process the custom RGB commands.

### Observed Limitation

The RGB changes were not persistent.

With the keyboard set to a static blue lighting mode, individual LEDs briefly turned red and then returned to blue.

This suggests that the original lighting engine continues to overwrite externally supplied RGB values.

The exact overwrite mechanism has not yet been conclusively identified.


### Dedicated External RGB Mode

The proposed approach is to introduce an external RGB control flag.

When enabled, the keyboard should preserve RGB values supplied by software instead of restoring colors from its onboard lighting modes.

When disabled, the keyboard should return to normal onboard lighting behavior.

### Proposed Protocol Extensions

| Subcommand | Proposed behavior |
|---|---|
| `0x02` | Set an individual LED color |
| `0x03` | Enable or disable external RGB mode |
| `0x04` | Update multiple LED colors |

Only `0x02` is implemented in V3.

The other commands are proposals and may change during development.

### Areas Requiring Investigation

- The lighting update loop.
- The interaction between RGB buffers and the framebuffer.
- The location where onboard lighting modes overwrite custom values.
- Efficient multi-LED updates.
- Persistent colors without continuous host-side retransmission.
- Safe switching between onboard and software-controlled lighting.
- Maintaining normal keyboard functionality while external RGB control is active.

## 11. Firmware Safety

**Flashing modified firmware can permanently disable a keyboard.**

Potential failure modes include:

- Invalid application firmware.
- Incorrect function addresses.
- Corrupted flash programming.
- USB enumeration failure.
- Inability to enter LDROM.
- Loss of normal keyboard functionality.

Although the tested keyboard successfully recovered from temporary bootloader-entry issues after a USB power cycle, this does not establish a reliable recovery procedure for corrupted firmware.

The project does not currently provide a guaranteed unbricking method.

Only tested firmware images should be used, and firmware should not be flashed onto unverified hardware.

## 12. Future Research

Longer-term firmware research may explore exposing additional keyboard functions through USB HID.

Potential capabilities include:

- Software-controlled lighting modes.
- Brightness and effect-speed adjustment.
- Keyboard configuration profiles.
- Key remapping.
- Macro management.
- Other settings currently controlled through keyboard shortcuts.

These capabilities are not yet implemented, and some may require additional firmware analysis or may not be feasible on the existing hardware.

The ultimate goal is to provide a reliable software interface for keyboard customization across Windows, Linux, and macOS.

---

## Disclaimer

This document describes experimental reverse-engineering findings for a specific keyboard and firmware image.

The project is independent and is not affiliated with or endorsed by Ducky or Nuvoton.

Function names, memory layouts, and protocol interpretations may change as research progresses.

All firmware modifications and flashing operations are performed at the user's own risk.