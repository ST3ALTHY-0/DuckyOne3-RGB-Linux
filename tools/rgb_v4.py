"""Repository CLI compatibility facade and optional Linux hidraw transport."""
import os
from pathlib import Path
import sys

if __package__:
    from .recovery import inspect_ducky_ldrom as hid
else:
    from recovery import inspect_ducky_ldrom as hid

# Keep the developer CLI runnable from a checkout without installing Qt.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller" / "src"))
try:
    from ducky_rgb.protocol import (BANKS, SLOTS, PIXELS, FRAME_BYTES, DESCRIPTOR, PREFIX,
                                    RGBController as WireController, Op, Status, Reply, packet,
                                    RGBError, CommandFailed, ConnectionLost, UnsupportedProtocol)
finally:
    sys.path.pop(0)


class LinuxHID:
    """Discover the verified APROM vendor collection through the shared HID helpers."""

    def __init__(self, device=None):
        path = hid.find_device(hid.APROM_PID)
        if not path or (device and Path(device).resolve() != Path(path)):
            raise ConnectionLost("No matching Ducky APROM vendor HID interface")
        descriptor = hid.HIDRAW_ROOT / Path(path).name / "device/report_descriptor"
        if descriptor.read_bytes() != DESCRIPTOR:
            raise UnsupportedProtocol("APROM vendor report descriptor does not match V1.16")
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NONBLOCK)

    def write(self, data):
        hid.write_report(self.fd, data)

    def read(self, timeout):
        return hid.read_reply(self.fd, "V4 RGB", timeout=timeout)

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


class RGBController(WireController):
    @classmethod
    def connect(cls, device=None, **options):
        transport = LinuxHID(device)
        client = cls(transport, **options)
        try:
            client.capabilities()
        except Exception:
            transport.close()
            raise
        return client
