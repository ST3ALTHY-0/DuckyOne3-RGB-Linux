# USB HID Protocol Documentation

> **AI-Assisted Research:** The USB HID protocol was investigated with significant assistance from AI Tools. Findings are based on firmware reverse engineering and experiments with a physical Ducky One 3 SF RGB keyboard. This document describes an experimental, unofficial protocol implementation.

## Overview

This document describes the USB HID communication used by the **Ducky One 3 SF RGB** keyboard, with particular emphasis on the custom RGB control protocol introduced by this project.

The goal is to establish a documented communication interface that software can use to control keyboard lighting and potentially other settings.

The protocol is intended to serve as the foundation for future keyboard configuration software supporting Windows, Linux, and macOS.

**Important:** The RGB commands described here are extensions implemented by modified firmware. They are not confirmed to work with the keyboard's original, unmodified firmware.

## 1. USB Device Identification

The keyboard exposes different USB identifiers depending on whether it is running its normal application firmware or its bootloader.

| Mode | Vendor ID | Product ID |
|---|---|---|
| Application (APROM) | `0x3233` | `0x5311` |
| Bootloader (LDROM) | `0x3233` | `0x5310` |

The application interface is used for normal keyboard operation and custom RGB commands.

The bootloader interface is used for firmware identification and updates.

These interfaces should not be confused. The custom RGB commands are intended for APROM, not LDROM.

### Device Discovery

Linux tools enumerate `/sys/class/hidraw/hidraw*`, match USB VID/PID, and locate the corresponding USB interface. They require HID class `0x03`, a 64-byte interrupt IN endpoint, and a 64-byte interrupt OUT endpoint. Multiple matches for a mode are rejected. Use the discovered node since hidraw numbers can change on reconnect.

The official updater recognizes `0416:3F00` as an alternative LDROM identifier. That identifier is untested on the project keyboard and is excluded from automatic discovery. A future cross-platform client will need an OS-appropriate HID backend.

### APROM reboot protocols

Both APROM protocols use `3233:5311`. The official updater supports both. The tools identify the application collection from the report descriptor.

| Firmware evidence | Usage page | Usage | Reboot payload prefix |
|---|---|---|---|
| Legacy protocol observed on V1.10 | `0x0001` | `0x0000` | `CC` |
| Tested on stock V1.16 and modified V3 | `0xFF00` | `0x0001` | `00 3A 01 09 01 04 00 01 01` |

Pad the payload to 64 bytes with zeros. Linux hidraw adds a leading zero report ID for a 65-byte host write. This leading report ID is separate from the initial zero in the newer payload. An unrecognized application collection is rejected. Earlier V1.16 recovery attempts sent the legacy command, which explains the failure to enter LDROM.

## 2. HID Report Descriptor

Stock V1.16 and the tested V3 firmware expose a vendor-defined HID interface.

The observed report descriptor is:

```text
06 00 FF 09 01 A1 01 19 01 29 40 15 00
26 FF 00 75 08 95 40 81 00 19 01 29 40
91 00 C0
```

### Descriptor Interpretation

| Descriptor element | Value | Meaning |
|---|---|---|
| Usage Page | `0xFF00` | Vendor-defined |
| Usage | `0x01` | Vendor-defined usage |
| Collection | Application | HID application collection |
| Report Size | 8 bits | One byte per field |
| Report Count | 64 | 64 bytes per report |
| Input | Data | 64-byte input report |
| Output | Data | 64-byte output report |

The descriptor does not explicitly declare a Report ID.

The HID report payload is therefore 64 bytes.

### Report ID Handling

On Linux, writes through `hidraw` include a leading report-ID byte even when the HID descriptor does not declare a Report ID.

For this interface, that byte is `0x00`.

Consequently:

```text
HID payload size:     64 bytes
Linux hidraw write:   65 bytes
```

Example:

```python
payload = bytearray(64)

with open("/dev/hidrawN", "wb", buffering=0) as device:
    device.write(b"\x00" + payload)
```

The extra byte is a host API convention, not part of the 64-byte RGB command payload.

Other operating systems and HID libraries may handle this differently.

## 3. Protocol Architecture

The modified firmware introduces a custom command dispatcher into the keyboard's existing USB command-processing path.

The dispatcher examines incoming HID reports and determines whether they contain a recognized custom command.

```text
Host Application
       |
       v
USB HID Output Report
       |
       v
Keyboard USB Receive Buffer
       |
       v
Custom Command Dispatcher
       |
       +---- Recognized RGB Command
       |              |
       |              v
       |       RGB Command Handler
       |
       +---- Other Commands
                      |
                      v
               Original Handler
```

The custom dispatcher is designed to preserve the original firmware's command handling for reports that do not match its custom RGB command header.

The current implementation does not provide a general-purpose command framework. It recognizes one specific custom RGB command.

## 4. Custom Command Header

The V3 firmware patch recognizes a command with the following header:

```text
00 3A 00 00 01 02
```

The first six bytes are interpreted as:

| Offset | Value | Purpose |
|---|---|---|
| `0` | `0x00` | Required header byte |
| `1` | `0x3A` | Command identifier |
| `2` | `0x00` | Required header byte |
| `3` | `0x00` | Required header byte |
| `4` | `0x01` | Protocol field |
| `5` | `0x02` | Set RGB command |

The meanings of the header fields are based on the custom implementation and observed firmware behavior.

The custom command is recognized only when all six bytes match the expected values.

Reports with a different header are forwarded to the original firmware command handler.

## 5. Set RGB Command — `0x02`

<escape>**Status: Implemented and tested in V3**</escape>

This command sets the RGB color of an individual logical LED address.

### Packet Layout

The command uses a 64-byte payload.

| Offset | Size | Field | Description |
|---|---|---|---|
| `0` | 1 byte | Header | `0x00` |
| `1` | 1 byte | Command | `0x3A` |
| `2` | 1 byte | Reserved | `0x00` |
| `3` | 1 byte | Reserved | `0x00` |
| `4` | 1 byte | Protocol | `0x01` |
| `5` | 1 byte | Subcommand | `0x02` |
| `6` | 1 byte | Bank | Logical LED row |
| `7` | 1 byte | Index | Logical LED column |
| `8` | 1 byte | Red | Red intensity |
| `9` | 1 byte | Green | Green intensity |
| `10` | 1 byte | Blue | Blue intensity |
| `11–63` | 53 bytes | Reserved | Ignored by the V3 RGB handler |

### Valid Values

| Field | Range |
|---|---|
| Bank | `0–4` |
| Index | `0–14` |
| Red | `0–255` |
| Green | `0–255` |
| Blue | `0–255` |

The dispatcher validates the bank and index before updating the RGB buffer.

The original firmware's logical LED mapping routine is also used to validate and translate the requested address.

### Example: Red

Set bank `0`, index `0` to red:

```text
00 3A 00 00 01 02 00 00 FF 00 00 00 ...
```

### Example: Green

Set bank `1`, index `4` to green:

```text
00 3A 00 00 01 02 01 04 00 FF 00 00 ...
```

### Example: Blue

Set bank `2`, index `7` to blue:

```text
00 3A 00 00 01 02 02 07 00 00 FF 00 ...
```

All packets are padded to 64 bytes.

### Example: Custom Color

Set bank `3`, index `5` to RGB `(128, 64, 255)`:

```text
00 3A 00 00 01 02 03 05 80 40 FF 00 ...
```

## 6. Python Packet Construction

A basic implementation of the RGB packet format:

```python
def create_rgb_report(bank, index, red, green, blue):
    if not 0 <= bank < 5:
        raise ValueError("Bank must be between 0 and 4")

    if not 0 <= index < 15:
        raise ValueError("Index must be between 0 and 14")

    for value in (red, green, blue):
        if not 0 <= value <= 255:
            raise ValueError("RGB values must be between 0 and 255")

    report = bytearray(64)

    report[1] = 0x3A
    report[4] = 0x01
    report[5] = 0x02

    report[6] = bank
    report[7] = index

    report[8] = red
    report[9] = green
    report[10] = blue

    return bytes(report)
```

### Sending the Report Through Linux hidraw

```python
def send_rgb(device_path, bank, index, red, green, blue):
    report = create_rgb_report(
        bank, index, red, green, blue
    )

    with open(device_path, "wb", buffering=0) as device:
        written = device.write(b"\x00" + report)

        if written != 65:
            raise IOError(
                f"Incomplete HID write: {written} bytes"
            )


send_rgb(
    "/dev/hidrawN",
    bank=0,
    index=0,
    red=255,
    green=0,
    blue=0,
)
```

This example uses Linux `hidraw` directly.

It is not a complete cross-platform implementation, and `/dev/hidrawN` is only an example path.

A successful write means the operating system accepted the report. It does not independently confirm that the keyboard applied the requested color.

## 7. LED Addressing

The custom RGB protocol uses two fields to identify an LED:

```text
Bank  = logical row
Index = logical column
```

The observed address space is five banks with fifteen indices per bank.

```text
        Index
        00 01 02 03 04 05 06 07 08 09 10 11 12 13 14

Bank 0  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Bank 1  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Bank 2  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Bank 3  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Bank 4  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
```

This provides 75 logical addresses.

It does not necessarily mean the keyboard contains 75 independent physical LEDs.

### Mapping Behavior

Initial testing indicates that:

- Banks generally correspond to physical keyboard rows.
- Indices generally correspond to positions across a row.
- Some larger keys correspond to multiple logical addresses.
- The spacebar appears to occupy several logical positions.

The exact physical-key mapping has not yet been fully documented.

The firmware contains a mapping function that translates logical addresses to internal LED positions.

The custom dispatcher uses this existing mapping functionality.

### Internal LED Identifier

The firmware encodes a logical LED address as:

```c
uint16_t led_id = (bank << 8) | index;
```

For example:

```text
Bank:  0x02
Index: 0x07

LED ID: 0x0207
```

The internal mapping routine translates this identifier before the RGB values are written.

## 8. RGB Color Representation

The USB command accepts three 8-bit RGB values.

Each channel has a range of:

```text
0–255
```

Internally, the identified firmware RGB-writing function uses 16-bit channel values.

The dispatcher converts each 8-bit value to 16-bit using:

```c
uint16_t value16 = value8 * 257;
```

This is equivalent to:

```c
uint16_t value16 = (value8 << 8) | value8;
```

### Examples

| 8-bit value | 16-bit value |
|---|---|
| `0` | `0x0000` |
| `1` | `0x0101` |
| `64` | `0x4040` |
| `128` | `0x8080` |
| `192` | `0xC0C0` |
| `255` | `0xFFFF` |

The resulting values are passed to the firmware's existing RGB-writing function.

## 9. RGB Update Behavior

After processing a valid RGB command, the dispatcher requests a lighting refresh by setting a firmware flag.

Identified refresh flag:

```text
0x200027B0
```

The custom command writes:

```c
*(volatile uint8_t *)0x200027B0 = 1;
```

The firmware's existing lighting routines subsequently process the updated RGB state.

### Current Limitation

In V3, custom colors are not persistent.

When the keyboard is configured with an onboard lighting mode, the requested RGB values are displayed briefly before being overwritten.

For example:

```text
Onboard mode: Static Blue

Host sends: Set LED to Red
                  |
                  v
             LED turns red
                  |
                  v
        Original lighting update
                  |
                  v
             LED returns blue
```

This has been observed during physical testing.

The precise function responsible for overwriting the custom colors has not yet been conclusively identified.

The planned V4 firmware will investigate a dedicated external RGB mode.

## 10. Testing the Address Space

The following test sends a red RGB command to every logical address.

```python
import time

device_path = "/dev/hidrawN"

with open(device_path, "wb", buffering=0) as device:
    for bank in range(5):
        for index in range(15):
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
                raise IOError("Incomplete HID write")

            time.sleep(0.03)
```

### Observed Results

This test successfully caused keys throughout the keyboard to flash red.

The results support the following conclusions:

1. The custom HID command is recognized by the modified firmware.
2. The RGB-writing function can be invoked through the custom dispatcher.
3. The logical address range reaches LEDs throughout the keyboard.
4. The original lighting engine continues to control the final displayed colors.

A complete mapping of all logical addresses to physical keys remains future work.

## 11. Command Responses and Acknowledgments

The current V3 RGB command is implemented as a host-to-device command.

It does not define a dedicated RGB acknowledgment response.

Consequently, host software cannot currently distinguish between:

- A successfully applied RGB update.
- A valid command that is subsequently overwritten by the lighting engine.
- A command that is rejected internally.
- A command delivered to an incompatible firmware implementation.

The dispatcher also silently returns for invalid LED addresses that match the custom RGB header.

Future protocol versions may introduce explicit status responses.

Possible status values could include:

| Status | Proposed meaning |
|---|---|
| `0x00` | Success |
| `0x01` | Invalid command |
| `0x02` | Invalid LED address |
| `0x03` | Unsupported operation |
| `0x04` | External RGB mode disabled |

**These status codes are proposals only. They are not implemented in V3.**

## 12. Proposed Future Commands

The following extensions are being considered for future firmware revisions.

They are not part of the currently implemented V3 protocol.

### `0x03` — External RGB Mode

**Status: Proposed**

Enable or disable software-controlled lighting.

Intended behavior:

```text
External RGB Enabled:
    Software controls LED colors.
    Onboard lighting does not overwrite them.

External RGB Disabled:
    Original keyboard lighting resumes.
```

A possible future packet could use byte `6` as the enable flag:

```text
00 3A 00 00 01 03 01 ...
```

Where:

```text
0x00 = Disable external RGB
0x01 = Enable external RGB
```

The exact format has not been finalized.

### `0x04` — Batch RGB Updates

**Status: Proposed**

Allow multiple LED colors to be updated in a single HID report.

The current V3 protocol requires one report per logical LED address.

Batching would reduce USB traffic and potentially improve animation performance.

A possible implementation could pack multiple LED entries into the 64-byte payload.

The final format will depend on firmware memory constraints, rendering behavior, and performance testing.

### Additional Future Commands

Potential future functionality includes:

- Global brightness control.
- Lighting effect selection.
- Lighting animation speed.
- Keyboard profile selection.
- Firmware capability discovery.
- Device information queries.
- Other keyboard configuration operations.

No command IDs or packet formats have been finalized for these features.

## 13. Cross-Platform Implementation

The protocol is based on USB HID rather than a Linux-specific device interface.

This makes it suitable for investigation on multiple operating systems.

### Windows

Potential implementation approaches include the Windows HID APIs or a cross-platform HID library.

### Linux

The current proof-of-concept tools communicate through `hidraw`.

A production implementation should support automatic device discovery and appropriate permissions.

### macOS

A future implementation could use Apple's HID APIs or a cross-platform HID library.

### Shared Protocol Layer

Ideally, the final application will separate packet construction from device communication.

```text
             Keyboard Application
                     |
                     v
               RGB Controller
                     |
                     v
              HID Protocol Layer
                     |
             +-------+-------+
             |       |       |
             v       v       v
          Windows  Linux   macOS
             |       |       |
             +-------+-------+
                     |
                     v
               Ducky Keyboard
```

The packet format can remain consistent even when the operating-system-specific HID transport differs.

No Windows or macOS support has yet been validated.

## 14. Bootloader Communication

The keyboard's LDROM bootloader uses a separate USB HID protocol for firmware management.

This is distinct from the custom RGB command protocol.

The following command identifiers were identified during bootloader investigation:

| Command | Purpose |
|---|---|
| `0xAE` | Connect to bootloader |
| `0xA4` | Synchronize packet numbering |
| `0xA6` | Read bootloader version |
| `0xB1` | Read MCU product ID |
| `0xA2` | Read configuration |
| `0xA0` | Program application firmware |
| `0xAB` | Run application firmware |

The tested bootloader uses packet sequencing and acknowledgments during firmware transfers.

The firmware flashing implementation and its associated risks are documented separately in [firmware.md](firmware.md).

Bootloader commands should not be sent to the application RGB interface unless their behavior has been specifically established.

## 15. Protocol Versioning

The current custom RGB command is identified using:

```text
Byte 4: 0x01
Byte 5: 0x02
```

Byte `4` is currently fixed at `0x01` by the custom dispatcher.

Although it is treated as a protocol field, V3 does not implement version negotiation.

Future versions should consider introducing:

- Explicit protocol version reporting.
- Firmware capability queries.
- Supported command discovery.
- Device identification.
- Structured error responses.
- Backward compatibility guarantees.

These additions would make it easier for a single software application to support multiple firmware versions and keyboard models.

## 16. Known Limitations

The current protocol implementation has several limitations:

- Requires modified firmware.
- Tested only on the Ducky One 3 SF RGB.
- Supports individual RGB updates only.
- Custom colors are overwritten by onboard lighting.
- No dedicated RGB command acknowledgments.
- No protocol version negotiation.
- No automatic physical-key mapping.
- No confirmed Windows or macOS implementation.
- No confirmed compatibility with other Ducky keyboards.

These limitations are expected to change as the project develops.

## 17. Future Research

Further investigation will focus on:

1. Persistent RGB control.
2. Efficient multi-LED updates.
3. Physical-key mapping.
4. Device capability detection.
5. RGB command acknowledgments.
6. Cross-platform HID communication.
7. Software control of additional keyboard settings.

The ultimate goal is a stable, documented interface that allows applications to manage keyboard customization without requiring users to navigate onboard keyboard shortcuts.

---

## Disclaimer

This protocol is experimental and unofficial.

The custom RGB commands require modified keyboard firmware and are not supported by Ducky.

Sending commands to incompatible firmware or using experimental flashing tools may cause unexpected behavior or device failure.

The project is not affiliated with or endorsed by Ducky or Nuvoton.
## V4 external RGB protocol

V4 uses the same 64-byte interrupt vendor collection and preserves the stock handler. The V4 namespace begins `00 3A 52 34 E4`. Its independent receive slot records the actual received length before OUT rearm. Host request tags match replies and distinguish retransmissions from stale endpoint traffic.

Use `tools/rgb_v4.py` for capability detection, session ownership, frame transactions and scanout status. The client supports explicit commit or an optional final-chunk commit. An accepted frame ID acknowledges assembly and CRC validation. A displayed ID acknowledges the stock scanout page selection. The [wire specification](reverse-engineering/v4-implementation-spec.md#exact-vendor-hid-v1-format) defines all opcodes, errors and overlay flags.
