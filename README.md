# Ducky One 3 RGB Control


> **AI-assisted development.** This project was developed with significant help from AI tools. I have tested V4 on a physical Ducky One 3 SF RGB keyboard and it worked as expected.

## Ducky RGB Studio

The [cross-platform desktop controller](controller/README.md) lives in `controller/` and installs separately. It provides a layered lighting editor, ANSI keyboard preview, calibration, and a simulator. The desktop app and Linux RGB CLI share the same V4 protocol client. Firmware builds, programming and recovery remain separate.

Install the controller with `python -m pip install ./controller` in a virtual environment. Run `ducky-rgb --simulate` to open the editor without accessing USB. See the controller documentation for platform setup and validation status.

## Compatibility

V4 was tested on one **Ducky One 3 SF RGB** using the exact stock **V1.16** firmware image.  The build and flash tools check the image, and the flasher also checks the keyboard’s bootloader and configuration. Other firmware versions and hardware revisions are untested. The command-line tools currently use Linux.

**Ducky_One_3_SF_RGB_V1.16 is required to be installed on keyboard for this firmware flash to work!**

Flashing experimental firmware can leave the keyboard unusable. Read the [USB recovery guide](tools/recovery/README.md) before programming. The stock firmware is proprietary and must be supplied separately.

## Getting started

Run these commands from the repository root. Python 3 is required. To build the firmware, also install Clang, LLD, LLVM objcopy, and GNU Arm binutils.

1. Build V4 from your original V1.16 firmware image.

   ```sh
   python3 firmware/build_patch.py /path/to/stock-v1.16.bin --version 4 --output ducky-v4.bin
   ```

2. Run the flasher's offline check, then program the keyboard if the check passes and you have reviewed the recovery guide.

   ```sh
   python3 tools/recovery/flash_v4.py ducky-v4.bin
   sudo python3 tools/recovery/flash_v4.py ducky-v4.bin --flash --confirm FLASH-DUCKY-V4
   ```

3. Preview a color, then send it to the keyboard running V4. Sending requires read/write access to the keyboard’s Linux HID device.

   ```sh
   python3 tools/ducky_rgb.py static ff2020
   python3 tools/ducky_rgb.py --send static ff2020
   ```

Press **Ctrl+C** to end the session and restore the keyboard’s built-in lighting. Run `python3 tools/ducky_rgb.py --help` for per-key colors, gradients, rainbow effects, and other options.

## Documentation

- [Firmware build and architecture](docs/firmware.md)
- [HID protocol](docs/hid-protocol.md) and [LED mapping](docs/led-mapping.md)
- [USB recovery](tools/recovery/README.md) and [hardware recovery](tools/recovery/hardware-recovery.md)
- [Reverse-engineering notes and V4 design](docs/reverse-engineering/README.md)


## License

Original project source code is licensed under [GPLv3](LICENSE) (`GPL-3.0-only`). Proprietary firmware and third-party components remain subject to their respective licenses. This is an independent project and is unaffiliated with Ducky and Nuvoton.
