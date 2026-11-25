#!/usr/bin/env python3

from recover_usb import FirmwareProfile, VERIFIED_IDENTITY, main

V4 = FirmwareProfile(
    "experimental V4",
    46352,
    "77a3cc8693052fa5be882f0331c84487a219a21f199e170722d53f4aa73c565f",
    "FLASH-DUCKY-V4",
    VERIFIED_IDENTITY,
)

if __name__ == "__main__":
    main(profile=V4)
