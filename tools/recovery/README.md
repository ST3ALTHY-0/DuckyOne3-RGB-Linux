# USB recovery

These tools use Linux hidraw for the Ducky One 3 SF RGB. Stock V1.16 restoration over USB was tested on the project keyboard. Provide your own original image and keep private backups outside version control.

## Detect, inspect, or change mode

Run from the project root. Disconnect other matching keyboards before changing modes.

```sh
python3 tools/recovery/recover_usb.py --detect
sudo python3 tools/recovery/recover_usb.py --inspect
```

Detection uses sysfs and leaves the current mode alone. Inspection uses an existing `3233:5310` LDROM connection or enters it from `3233:5311` using the [descriptor-selected reboot protocol](../../docs/hid-protocol.md#aprom-reboot-protocols). It prints the MCU and configuration even if they do not match a programming profile. After successful inspection it requests APROM and waits for it to reappear. If you only have one keyboard, use this combined operation to regain typing automatically.

For an existing LDROM session, add `--bootloader-only` to inspection or flashing. Use `--inspect --stay-in-bootloader` when you want to keep LDROM active. Have a separate input method or arrange the next step first.

```sh
sudo python3 tools/recovery/recover_usb.py --enter-bootloader
sudo python3 tools/recovery/recover_usb.py --exit-bootloader
```

Enter and exit are standalone operations and do not program flash. Exit requests APROM, so only use it when the application is expected to be intact.

## Restore stock V1.16

The first command validates the image and constructs packets offline. Programming requires the second command's explicit confirmation. Omit `--bootloader-only` to let the utility enter LDROM from working APROM.

```sh
python3 tools/recovery/recover_usb.py /path/to/vendor_v1.16.bin
sudo python3 tools/recovery/recover_usb.py /path/to/vendor_v1.16.bin --bootloader-only --flash --confirm RESTORE-DUCKY-1.16
```

The programming profile requires the exact 42,942-byte stock image and the verified LDROM version, MCU product ID and configuration words. A configuration mismatch stops programming. The V3 flasher applies the same device checks to the separate 43,084-byte V3 profile. Neither tool changes configuration registers.

Stock uses 767 programming packets and V3 uses 770. Each transfer starts at the beginning of the image. If programming starts and then fails or is interrupted, the tool does not request APROM or retry. Failures before programming, during inspection, during programming, and returning to APROM are reported separately. After a completed transfer, verify typing, lighting, and LDROM access. Enumeration and packet acknowledgments are functional checks.

## Limits

USB recovery depends on accessible LDROM. Independent entry with completely corrupted APROM, recovery from interrupted programming, and recovery from corrupted LDROM or MCU configuration remain unproven. Full firmware readback, byte-for-byte verification, and complete Data Flash backup and restoration are unavailable. It is unknown whether a shorter restoration erases all bytes left beyond the stock image. The successful stock restoration demonstrates normal operation and loss of the custom RGB behavior. Factory flash equivalence remains unverified.

The official updater has configuration-reading functionality. No arbitrary flash readback command has been verified. Avoid undocumented commands and deliberate corruption until independent recovery is established. See the [hardware recovery guide](hardware-recovery.md) for the untested SWD/ICP path.
