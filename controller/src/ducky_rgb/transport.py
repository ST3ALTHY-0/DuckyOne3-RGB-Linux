"""HID interfaces carry unnumbered 64-byte payloads at the protocol boundary."""
from dataclasses import dataclass
from typing import Protocol

from .protocol import ConnectionLost, DESCRIPTOR


class Transport(Protocol):
    def write(self, data: bytes) -> None: ...
    def read(self, timeout: float) -> bytes: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class Endpoint:
    path: bytes
    label: str
    interface: int = -1
    simulator: bool = False
    vid: int = 0x3233
    pid: int = 0x5311
    backend: str = "HIDAPI"


def vendor_descriptor(data: bytes) -> bool:
    """Check collection and report shapes even if a host reconstructs HID items."""
    if data == DESCRIPTOR:
        return True
    if not data or len(data) > 4096:
        return False
    page = usage = size = count = depth = collections = input_bits = output_bits = 0
    globals_stack = []
    position = 0
    while position < len(data):
        header = data[position]
        position += 1
        width = (0, 1, 2, 4)[header & 3]
        if header == 0xfe or position+width > len(data):
            return False
        value = int.from_bytes(data[position:position+width], "little")
        position += width
        tag = header & 0xfc
        if tag == 0x04:
            page = value
        elif tag == 0x08:
            usage = value
        elif tag == 0x74:
            size = value
        elif tag == 0x94:
            count = value
        elif tag == 0x84:
            return False
        elif tag == 0xa4:
            globals_stack.append((page, size, count))
        elif tag == 0xb4:
            if not globals_stack:
                return False
            page, size, count = globals_stack.pop()
        elif tag == 0xa0:
            if not depth:
                collections += 1
                combination = usage if usage > 0xffff else (page << 16) | usage
                if collections != 1 or value != 1 or combination != 0xff000001:
                    return False
            depth += 1
        elif tag == 0xc0:
            depth -= 1
            if depth < 0:
                return False
        elif tag in (0x80, 0x90, 0xb0):
            if not depth or tag == 0xb0:
                return False
            if tag == 0x80:
                input_bits += size*count
            else:
                output_bits += size*count
        if not header & 0x0c:
            usage = 0
    return not depth and collections == 1 and input_bits == output_bits == 512 and not globals_stack


class HIDBackend:
    def __init__(self, binding=None):
        if binding is None:
            import hid as binding
        self.hid = binding

    def enumerate(self) -> list[Endpoint]:
        matches = {}
        for info in self.hid.enumerate(0x3233, 0x5311):
            if (info.get("vendor_id"), info.get("product_id"),
                info.get("usage_page"), info.get("usage")) != (0x3233, 0x5311, 0xFF00, 1):
                continue
            interface = info.get("interface_number", -1)
            if interface not in (-1, 0, None):
                continue
            path = info.get("path")
            if not isinstance(path, bytes) or not path:
                continue
            matches[path] = Endpoint(path, info.get("product_string") or "Ducky One 3 SF RGB",
                                     interface if interface is not None else -1)
        return sorted(matches.values(), key=lambda endpoint: endpoint.path)

    def open(self, endpoint: Endpoint) -> Transport:
        if endpoint not in self.enumerate():
            raise ConnectionLost("The selected vendor collection is no longer present")
        device = self.hid.device()
        try:
            device.open_path(endpoint.path)
            descriptor = getattr(device, "get_report_descriptor", None)
            if descriptor:
                try:
                    raw = bytes(descriptor() or b"")
                except (OSError, NotImplementedError):
                    raw = b""
                if raw and not vendor_descriptor(raw):
                    raise ConnectionLost("Unexpected vendor report descriptor")
        except BaseException:
            device.close()
            raise
        return HIDTransport(device)


class HIDTransport:
    def __init__(self, device):
        self.device = device

    def write(self, data: bytes):
        if len(data) != 64:
            raise ValueError("Expected 64-byte HID payload")
        if self.device.write(b"\0" + data) != 65:
            raise OSError("Short HID output report")

    def read(self, timeout: float) -> bytes:
        data = bytes(self.device.read(65, max(1, int(timeout * 1000 + 0.999))))
        if not data:
            raise TimeoutError("HID input timed out")
        if len(data) == 65 and data[0] == 0:
            return data[1:]
        return data

    def close(self):
        self.device.close()
