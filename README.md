# Ducky One 3 RGB on Linux

Experimental tools and firmware patch for the Ducky One 3 SF RGB. The patch adds a per-key RGB command to the application firmware.

## Build the patch offline

Use Python 3, Clang with ARM target support, LLD, and llvm-objcopy. Supply your own original firmware image.

```sh
python3 firmware/build_patch.py /path/to/ducky_one3_sf_firmware.bin --output /tmp/ducky-rgb.bin
```

## Preview an RGB report

```sh
python3 tools/send_rgb.py --bank 1 --index 4 --red 255 --green 64 --blue 0
```

See the [firmware notes](docs/firmware.md), [HID protocol](docs/hid-protocol.md), and [LED mapping](docs/led-mapping.md).
