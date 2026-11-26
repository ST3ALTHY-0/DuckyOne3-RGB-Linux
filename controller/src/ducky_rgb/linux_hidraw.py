"""Linux fallback for verified vendor collections absent from HIDAPI discovery."""
import os
from pathlib import Path
import select

from .protocol import ConnectionLost
from .transport import Endpoint, vendor_descriptor


class LinuxVendorBackend:
    def __init__(self, primary=None, *, sysfs=Path("/sys/class/hidraw"), dev=Path("/dev")):
        self.primary, self.sysfs, self.dev = primary, sysfs, dev

    def raw_devices(self):
        endpoints = []
        for child in sorted(self.sysfs.glob("hidraw*")):
            if not child.name.removeprefix("hidraw").isdigit():
                continue
            try:
                info = dict(line.split("=", 1) for line in
                            (child/"device/uevent").read_text().splitlines() if "=" in line)
                if info.get("HID_ID", "").upper() != "0003:00003233:00005311":
                    continue
                if not vendor_descriptor((child/"device/report_descriptor").read_bytes()):
                    continue
            except OSError:
                continue
            endpoints.append(Endpoint(os.fsencode(self.dev/child.name), "Ducky One 3 SF RGB",
                                      0, backend="Linux hidraw"))
        return endpoints

    def enumerate(self):
        primary = self.primary.enumerate() if self.primary else []
        raw = self.raw_devices()
        # A libusb backend can use opaque paths. Prefer it when it already
        # sees the same number of vendor interfaces to avoid duplicate entries.
        if any(not device.path.startswith(b"/dev/hidraw") for device in primary):
            return primary if len(primary) >= len(raw) else raw
        paths = {endpoint.path for endpoint in primary}
        return primary + [endpoint for endpoint in raw if endpoint.path not in paths]

    def open(self, endpoint):
        if endpoint.backend != "Linux hidraw":
            try:
                return self.primary.open(endpoint)
            except OSError:
                fallback = next((raw for raw in self.raw_devices() if raw.path == endpoint.path), None)
                if fallback is None:
                    raise
                endpoint = fallback
        if endpoint not in self.raw_devices():
            raise ConnectionLost("The verified vendor collection disconnected")
        try:
            fd = os.open(endpoint.path, os.O_RDWR | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        except PermissionError as exc:
            raise PermissionError("Install Studio’s vendor-interface udev rule, then replug the keyboard") from exc
        except FileNotFoundError as exc:
            raise ConnectionLost("Linux detected the keyboard, but this environment cannot access its HID device node") from exc
        return HidrawTransport(fd)


class HidrawTransport:
    def __init__(self, fd):
        self.fd = fd

    def write(self, data):
        if len(data) != 64:
            raise ValueError("Expected 64-byte HID payload")
        if os.write(self.fd, b"\0"+data) != 65:
            raise OSError("Short HID output report")

    def read(self, timeout):
        if not select.select([self.fd], [], [], timeout)[0]:
            raise TimeoutError("HID input timed out")
        data = os.read(self.fd, 65)
        if not data:
            raise OSError("HID device disconnected")
        return data[1:] if len(data) == 65 and data[0] == 0 else data

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)
