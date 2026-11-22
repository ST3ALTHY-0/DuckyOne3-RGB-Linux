# Ducky One 3 — Software RGB & Keyboard Control

> **AI-Assisted Development**
>
> This project was developed with significant assistance AI tools.
>
> All major functionality has been developed through experimentation with physical hardware. AI-generated code and technical findings are tested and refined against a real Ducky One 3 SF RGB keyboard.
>
> As this is an experimental reverse-engineering project, AI-generated code and findings should be independently reviewed before use, particularly when modifying firmware.
>
> This code and repo is still mostly for my own use and I plan to polish it when I actually get the functionality I want.
> 

## Overview

**Ducky One 3 Software Control** is an open-source project aimed at bringing comprehensive software-based customization to Ducky One 3 keyboards.

The primary goal is to allow users to configure their keyboard's **RGB lighting directly through software**, rather than relying on physical keyboard shortcuts to cycle through effects, select colors, and adjust settings.

Ducky One 3 keyboards provide extensive onboard customization, but many settings must be adjusted through combinations of physical keys. This can make configuration inconvenient, especially when working with individual keys, custom lighting patterns, or multiple profiles.

This project aims to replace those manual interactions with a convenient software interface while expanding the keyboard's customization capabilities.

The long-term vision is a cross-platform keyboard management application supporting **Windows, Linux, and macOS**, with the potential to control additional keyboard features beyond RGB lighting.

### Project Goals

- **Software-controlled RGB:** Change colors, brightness, lighting modes, and effects through an application.
- **Per-key customization:** Assign colors to individual keys without navigating onboard keyboard shortcuts.
- **Custom lighting effects:** Create animations, gradients, waves, and other effects beyond the keyboard's built-in presets.
- **Profiles:** Save, load, and switch between custom keyboard configurations.
- **Cross-platform support:** Develop software compatible with Windows, Linux, and macOS.
- **Additional keyboard controls:** Investigate software access to other keyboard settings currently controlled through physical shortcuts.
- **Hardware compatibility:** Explore support for additional Ducky One 3 models and potentially other Ducky keyboards.

The project currently focuses on the **Ducky One 3 SF RGB**, which serves as the development and testing platform.

Other Ducky One 3 keyboards may be able to use the firmare tools to flash your own firmware your model, but please dont flash any firmware made for the One 3 SF to another model.

Other Ducky series keyboards should not use the firmware flasher for their own keyboard without modifying it for your board. Every firmware I have looked at outside the One 3 family is substanially different enough that I am dont believe it will work without heavy modification.

---

## Development Status

**Experimental — Working RGB Proof of Concept**

The first major milestone has been achieved: custom firmware successfully receives RGB commands from a computer and changes individual keyboard LEDs.

| Feature | Status |
|---|---|
| USB HID communication | Working |
| Custom firmware development | Working |
| Firmware flashing | Tested |
| Individual LED color control | Working, temporary |
| RGB row/column addressing | Identified |
| Persistent per-key RGB colors | In development |
| Software lighting mode selection | Planned |
| Software brightness control | Planned |
| Custom RGB effects | Planned |
| RGB profiles | Planned |
| Graphical configuration application | Planned |
| Windows support | Planned |
| Linux support | Planned |
| macOS support | Planned |
| Additional keyboard settings | Future goal |

### What Works Right Now?

The current V3 firmware patch allows the keyboard to receive custom USB HID commands specifying an LED address and RGB color.

Testing has confirmed that these commands can successfully change the colors of individual keys.

However, the keyboard's original lighting engine currently overwrites these changes almost immediately.

For example:

1. The keyboard is configured to display solid blue.
2. Software sends a command to change a specific key to red.
3. The selected key briefly turns red.
4. The keyboard's built-in lighting engine restores the original blue color.

This demonstrates that direct software control of individual LEDs is possible, but persistent control still requires further firmware development.

The next major milestone is implementing a dedicated software-controlled RGB mode that prevents the original lighting engine from overwriting custom colors.

---

## Why This Project Exists

The Ducky One 3 series includes onboard RGB configuration features, but these are primarily accessed through keyboard shortcuts.

For example, changing lighting effects or selecting colors may require combinations such as `Fn + Alt + T` or `Fn + Alt + Spacebar`.

While this approach works, it introduces several limitations:

- Customization requires remembering keyboard shortcuts.
- Selecting specific colors can be inconvenient.
- Per-key customization is difficult to manage.
- Creating complex lighting effects is impractical.
- Saving and managing multiple configurations is limited.
- Keyboard settings are not conveniently accessible through a graphical interface.

This project aims to make those capabilities accessible through software.

Instead of manually configuring the keyboard using its physical controls, users should eventually be able to open an application, select a key, choose a color, and immediately see the result.

The goal is not simply to reproduce the keyboard's existing functionality, but to make it more accessible and extensible.

---

## Planned Software Features

### RGB Lighting Control

The primary focus of the project.

Planned functionality includes:

- Full-keyboard color selection.
- Individual key color customization.
- Brightness adjustment.
- Lighting mode selection.
- Custom RGB animations.
- Gradients and color transitions.
- Customizable lighting speed and direction.
- Lighting presets and profiles.

### Visual Keyboard Editor

A future graphical interface will display a representation of the keyboard.

Users will be able to select individual keys or groups of keys and modify their lighting settings.

The intended workflow is straightforward:

1. Open the keyboard configuration application.
2. Select one or more keys.
3. Choose a color or lighting effect.
4. Apply the changes immediately.
5. Save the configuration as a reusable profile.

### Cross-Platform Support

The long-term goal is to support:

- Windows
- Linux
- macOS

The keyboard communicates through USB HID, making a cross-platform implementation a realistic goal.

However, operating-system support will depend on device access, permissions, and testing. The current proof-of-concept tools have been tested on Linux; Windows and macOS implementations have not yet been developed or validated.

### Additional Keyboard Controls

Beyond RGB lighting, future development may investigate whether other onboard keyboard settings can be controlled through software.

Potential areas include:

- Key remapping.
- Macro configuration.
- Keyboard profiles.
- Lighting-related shortcuts and settings.
- Other configurable firmware features.

These are research goals, not confirmed capabilities. Their feasibility will depend on the keyboard's hardware and firmware.

---

## How It Works

The Ducky One 3 SF RGB uses a Nuvoton microcontroller to manage keyboard input, USB communication, and RGB lighting.

The original firmware contains internal routines for mapping LED addresses, updating RGB values, and rendering lighting effects.

Through firmware reverse engineering, we identified several of these routines and developed a custom ARM Thumb assembly patch that allows the keyboard to recognize additional USB HID commands.

Rather than replacing the keyboard's entire firmware, the patch extends the existing firmware with a custom command handler.

### Communication Architecture

```text
       Keyboard Control Application
                   |
                   |
              USB HID
                   |
                   v
          Ducky One 3 Keyboard
                   |
                   v
          Custom Command Handler
                   |
           +-------+-------+
           |               |
           v               v
     RGB Commands     Original Commands
           |               |
           v               v
     RGB LED Buffer   Original Firmware
           |
           v
     Lighting Renderer
           |
           v
       Keyboard LEDs
```

The goal is to expose more of the keyboard's existing functionality to external software while preserving normal keyboard operation.

---

## Supported Hardware

### Currently Tested

| Component | Details |
|---|---|
| Keyboard | Ducky One 3 SF RGB |
| Microcontroller | Nuvoton NUC1261SG4AE |
| CPU architecture | ARM Cortex-M0 |
| Application USB VID:PID | `3233:5311` |
| Bootloader USB VID:PID | `3233:5310` |
| Bootloader version | `0x33` |
| MCU product ID | `0x01205212` |

Other Ducky One 3 models may use similar hardware or firmware, but compatibility has not yet been established.

**Do not flash the experimental firmware onto an unverified keyboard model or hardware revision.**

---

## Custom RGB Protocol

The current firmware patch introduces a custom RGB command using the keyboard's USB HID interface.

The command contains a logical LED address and RGB color values.

### Packet Format

The custom HID payload is 64 bytes.

| Byte offset | Description |
|---|---|
| `0` | Reserved (`0x00`) |
| `1` | Command identifier (`0x3A`) |
| `2–3` | Reserved |
| `4` | Protocol identifier (`0x01`) |
| `5` | RGB command (`0x02`) |
| `6` | LED bank / row |
| `7` | LED index / column |
| `8` | Red (0–255) |
| `9` | Green (0–255) |
| `10` | Blue (0–255) |
| `11–63` | Reserved |

### Example

Set logical LED `(0, 0)` to red:

```text
00 3A 00 00 01 02 00 00 FF 00 00 ...
```

This corresponds to:

```python
bank = 0
index = 0

red = 255
green = 0
blue = 0
```

The current implementation supports five banks and fifteen indices per bank.

### LED Mapping

Initial testing identified a logical **5 × 15 LED addressing grid**.

```text
           Columns
           0  1  2  3  4  5  6  7  8  9 10 11 12 13 14

Row 0      .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Row 1      .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Row 2      .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Row 3      .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
Row 4      .  .  .  .  .  .  .  .  .  .  .  .  .  .  .
```

The grid generally follows the physical keyboard layout. i.e (row 0, index 0: Esc Key and row 4, index 14: right arrow key)

Some larger keys, such as the spacebar, correspond to multiple logical positions. Further testing is needed to determine the exact mapping and whether those positions are aliases for the same LED.

A complete physical-key mapping is planned for the software configuration application.

---

## Firmware Development

The project currently uses a modified version of the Ducky One 3 SF RGB application firmware.

### V3 Firmware Patch

The V3 patch introduces a custom RGB command dispatcher that:

1. Receives USB HID reports.
2. Recognizes custom RGB commands.
3. Validates the requested LED address.
4. Uses the firmware's existing LED mapping routine.
5. Writes RGB values through an existing internal function.
6. Requests a lighting refresh.
7. Forwards unrelated commands to the original firmware handler.

### Firmware Details

| Property | Value |
|---|---|
| Original firmware size | 42,942 bytes |
| V3 firmware size | 43,084 bytes |
| Custom dispatcher offset | `0xA7C0` |
| Modified handler call offset | `0x9646` |

The original firmware image used for development has SHA-256:

```text
966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844
```

The tested V3 patched image has SHA-256:

```text
78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258
```

The patch is specific to this firmware image. Function addresses and memory layouts may differ in other versions.

### Building

The repository contains source code for the firmware patch and build tools.

The original proprietary firmware image is not distributed.

Example build command:

```bash
python3 build_patch.py \
  ../ducky_one3_sf_firmware.bin \
  --output ducky_one3_sf_rgb_v3.bin
```

Users must provide a compatible original firmware image.

---

## Firmware Flashing

> **Warning: Experimental firmware**
>
> Flashing modified firmware carries a risk of rendering the keyboard unusable. Recovery is not guaranteed.
>
> This project is not affiliated with or endorsed by Ducky or Nuvoton. Firmware modifications are performed entirely at the user's own risk.

The keyboard uses a Nuvoton bootloader that supports updating its application firmware over USB HID.

The project includes experimental tools for identifying the bootloader and transferring firmware.

### Bootloader Identification

```bash
sudo python3 inspect_ducky_ldrom.py
```

This script requests entry into the bootloader, reads device information, and attempts to return the keyboard to normal application mode.

### Flashing V3

Dry run:

```bash
python3 flash_ducky_v3.py ducky_one3_sf_rgb_v3.bin
```

Firmware programming:

```bash
sudo python3 flash_ducky_v3.py \
  ducky_one3_sf_rgb_v3.bin \
  --flash \
  --confirm FLASH-DUCKY-V3
```

During development, the V3 image was successfully transferred in 770 packets. The bootloader acknowledged all packets, and the keyboard resumed normal operation.

These acknowledgments do not constitute full flash readback verification.

**The flashing tools are experimental and should not be considered production-ready.**

---

## Roadmap

### Phase 1 — Firmware Research and Proof of Concept

- [x] Identify the keyboard's USB HID interfaces.
- [x] Establish communication with the Nuvoton bootloader.
- [x] Analyze the original application firmware.
- [x] Identify internal RGB-related functions.
- [x] Implement a custom RGB command handler.
- [x] Build and flash modified firmware.
- [x] Confirm the keyboard continues to function normally.
- [x] Successfully change individual LED colors.
- [x] Identify the logical LED grid.

### Phase 2 — Persistent Software RGB Control

- [ ] Identify why the built-in lighting engine overwrites custom RGB values.
- [ ] Implement a dedicated software-controlled RGB mode.
- [ ] Enable and disable external RGB control.
- [ ] Preserve externally assigned RGB values.
- [ ] Implement efficient multi-key RGB updates.
- [ ] Improve firmware safety and validation.

### Phase 3 — Keyboard Configuration Software

- [ ] Develop a reusable RGB control library.
- [ ] Implement automatic keyboard detection.
- [ ] Create a complete physical-key LED map.
- [ ] Build a graphical keyboard editor.
- [ ] Implement per-key color selection.
- [ ] Add software brightness and lighting controls.
- [ ] Add custom lighting effects and animations.
- [ ] Support saved profiles and presets.

### Phase 4 — Cross-Platform Support

- [ ] Windows application support.
- [ ] Linux application support.
- [ ] macOS application support.
- [ ] Cross-platform device detection and communication.
- [ ] Packaging and distribution.

### Phase 5 — Expanded Keyboard Functionality

- [ ] Investigate software key remapping.
- [ ] Investigate macro configuration.
- [ ] Explore additional onboard keyboard settings.
- [ ] Research compatibility with other Ducky models.

---

## Contributing

Contributions and technical research are welcome.

Particularly useful areas include firmware reverse engineering, USB HID communication, RGB rendering, graphical application development, cross-platform compatibility, and hardware testing.

Testing on additional Ducky One 3 hardware revisions may help establish broader compatibility.

Please include hardware and firmware information when reporting bugs or submitting test results.

Do not submit proprietary firmware images or vendor software binaries.

## Disclaimer

This is an independent, unofficial project and is not affiliated with Ducky or Nuvoton.

Ducky and Nuvoton are trademarks of their respective owners.

Firmware modification can damage or disable hardware. No warranty or guarantee of recovery is provided.

## License

The original project source code is licensed under the [GNU General Public License, version 3](LICENSE) (GPL-3.0-only). Proprietary firmware and third-party components remain subject to their respective licenses.
