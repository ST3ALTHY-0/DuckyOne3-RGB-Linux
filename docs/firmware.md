# Firmware

APROM contains the application firmware and enumerates as USB device `3233:5311`. LDROM contains the bootloader and enumerates as `3233:5310`.

The offline patch builder checks the original image size, SHA-256, and hook bytes. It links the Cortex-M0 Thumb dispatcher at `0xA7C0` and installs a branch-with-link at `0x9646`.

`tools/inspect_ducky_ldrom.py` requests LDROM, reads the bootloader version, MCU product ID, and configuration words, then requests APROM. `tools/flash_ducky_v3.py` defaults to a dry run and identifies the expected firmware image by SHA-256.
