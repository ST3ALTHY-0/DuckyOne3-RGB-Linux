#!/usr/bin/env python3
"""Program the verified V3 RGB firmware. Dry run by default."""
from recovery.recover_usb import V3, main


if __name__ == "__main__":
    main(profile=V3)
