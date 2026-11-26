"""Transport-independent V4 wire client shared with the repository CLI."""
from dataclasses import dataclass
from enum import IntEnum
import secrets
import struct
import time
import zlib

PREFIX = bytes.fromhex("00 3a 52 34 e4")
DESCRIPTOR = bytes.fromhex(
    "06 00 ff 09 01 a1 01 19 01 29 40 15 00 26 ff 00 75 08 95 40 81 00 19 01 29 40 91 00 c0")
BANKS, SLOTS, PIXELS = 5, 15, 75
FRAME_BYTES = PIXELS * 3


class Op(IntEnum):
    CAPS = 1
    MODE = 2
    CHUNK = 3
    COMMIT = 4
    STATUS = 5
    ABORT = 6
    BRIGHTNESS = 7
    OVERLAYS = 8
    KEEPALIVE = 9
    CHUNK_COMMIT = 10


class Status(IntEnum):
    OK = 0
    BAD_LENGTH = 1
    BAD_VERSION = 2
    BAD_OPCODE = 3
    BAD_ARGUMENT = 4
    WRONG_SESSION = 5
    NOT_READY = 6
    BUSY = 7
    INCOMPLETE = 8
    CONFLICT = 9
    BAD_CRC = 10
    STALE_SEQUENCE = 11
    UNSUPPORTED = 12
    INTERNAL_FAULT = 13


class RGBError(RuntimeError):
    pass


class UnsupportedProtocol(RGBError):
    pass


class ConnectionLost(RGBError):
    pass


class CommandFailed(RGBError):
    def __init__(self, op, reply):
        self.reply = reply
        super().__init__(f"{op.name}: {reply.status.name} (coverage {reply.coverage:#04x})")


@dataclass(frozen=True)
class Reply:
    status: Status
    mode: int
    coverage: int
    staged: int
    accepted: int
    queued: int
    displayed: int
    revision: int
    displayed_revision: int
    brightness: int
    overlays: int
    supported_overlays: int
    features: int
    layout: int
    geometry: tuple
    lease_ms: int
    flags: int

    @classmethod
    def decode(cls, data):
        fields = struct.unpack_from("<BB4H2IHBBII", data, 14)
        return cls(Status(data[7]), *fields, tuple(data[44:50]),
                   struct.unpack_from("<H", data, 50)[0], data[52])


def packet(op, arg=0, token=0, seq=0, data=b"", *, tag, version=1):
    if len(data) > 48 or not 0 < tag <= 65535:
        raise ValueError("Invalid V4 body or request tag")
    header = struct.pack("<5sBBBIH", PREFIX, version, int(op), arg, token, seq)
    return (header + data).ljust(62, b"\0") + struct.pack("<H", tag)


class RGBController:
    """One outstanding request and one external session per controller."""

    def __init__(self, transport, *, timeout=0.25, retries=3):
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.tag = secrets.randbelow(65535)
        self.token = 0
        self.seq = 0
        self.lease_ms = 0
        self.initial_overlays = 0
        self.session_ready = False
        self.frame = bytes(FRAME_BYTES)
        self._uncertain = None
        self.caps = None
        self.timeout_count = self.retry_count = 0

    def request(self, op, *, arg=0, seq=0, data=b"", token=None, version=1,
                allowed=(Status.OK,)):
        token = self.token if token is None else token
        self.tag = self.tag % 65535 + 1
        tx = packet(op, arg, token, seq, data, tag=self.tag, version=version)
        for attempt in range(self.retries):
            self.retry_count += int(attempt > 0)
            try:
                self.transport.write(tx)
                deadline = time.monotonic() + self.timeout
                while (remaining := deadline - time.monotonic()) > 0:
                    rx = self.transport.read(remaining)
                    if (len(rx) != 64 or rx[:5] != PREFIX or rx[6] != tx[6] | 0x80
                            or rx[8:14] != tx[8:14] or rx[53] != arg or rx[62:] != tx[62:]):
                        continue
                    if rx[5] != 1:
                        raise UnsupportedProtocol(f"Incompatible V4 major {rx[5]}")
                    try:
                        reply = Reply.decode(rx)
                    except ValueError as exc:
                        raise RGBError("Unknown firmware response status") from exc
                    if reply.status not in allowed:
                        raise CommandFailed(op, reply)
                    return reply
            except (TimeoutError, BlockingIOError):
                pass
            except OSError as exc:
                raise ConnectionLost(str(exc)) from exc
            self.timeout_count += 1
        raise TimeoutError(f"No matching V4 reply for {op.name}")

    def capabilities(self):
        try:
            reply = self.request(Op.CAPS, token=0, version=0)
        except TimeoutError as exc:
            raise UnsupportedProtocol("No V4 response. Stock and V3 do not implement discovery") from exc
        if (reply.layout != 0x01160001 or reply.geometry != (75, 5, 15, 16, 5, 64)
                or reply.features & 3 != 3):
            raise UnsupportedProtocol("Unexpected firmware geometry or capabilities")
        self.caps = reply
        return reply

    def external(self, *, lease_ms=0, overlays=0):
        if lease_ms != 0 and not 1000 <= lease_ms <= 60000:
            raise ValueError("Lease must be 0 or 1,000–60,000 ms")
        if not self.caps:
            self.capabilities()
        if not 0 <= overlays <= 15 or overlays & ~self.caps.supported_overlays:
            raise ValueError("Unsupported overlay mask")
        if self.token:
            raise RGBError("Close the current external session first")
        self.token = secrets.randbelow(0xFFFFFFFF) + 1
        self.lease_ms, self.initial_overlays = lease_ms, overlays
        try:
            reply = self.request(Op.MODE, arg=1, data=struct.pack("<HB", lease_ms, overlays))
        except CommandFailed:
            self.token = 0
            raise
        self.seq = 0
        self.frame = bytes(FRAME_BYTES)
        self._uncertain = None
        self.session_ready = True
        return reply

    def native(self, token=None):
        selected = self.token if token is None else token
        if not selected:
            raise ValueError("Native mode request requires the active token")
        if not 0 < selected <= 0xFFFFFFFF:
            raise ValueError("Session token out of range")
        result = self.request(Op.MODE, token=selected)
        deadline = time.monotonic() + 0.75
        while result.mode:
            if time.monotonic() >= deadline:
                raise TimeoutError("Native ownership transition is still pending")
            time.sleep(0.002)
            result = self.request(Op.STATUS, token=0)
        if selected == self.token:
            self.token = 0
            self.session_ready = False
        return result

    def status(self):
        return self.request(Op.STATUS)

    def brightness(self, value):
        if not 0 <= value <= 65535:
            raise ValueError("Brightness must be 0–65535")
        return self.request(Op.BRIGHTNESS, data=struct.pack("<H", value))

    def overlays(self, mask):
        if not 0 <= mask <= 15:
            raise ValueError("Overlay mask must be 0–15")
        return self.request(Op.OVERLAYS, arg=mask)

    def keepalive(self):
        return self.request(Op.KEEPALIVE)

    def wait_displayed(self, seq=None, *, timeout=0.75, revision=None):
        seq = self.seq if seq is None else seq
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            reply = self.status()
            if reply.displayed == seq and (revision is None or reply.displayed_revision == revision):
                return reply
            time.sleep(0.002)
        raise TimeoutError(f"Frame {seq} was not observed in scanout")

    def _reconcile(self):
        if self._uncertain is None:
            return
        sequence, frame = self._uncertain
        if self.status().accepted == sequence:
            self.seq, self.frame = sequence, frame
        else:
            self.request(Op.ABORT, seq=sequence)
        self._uncertain = None

    def set_frame(self, rgb, *, fast=False):
        if isinstance(rgb, int):
            raise ValueError("Expected RGB8 bytes or channel values")
        rgb = bytes(rgb)
        if len(rgb) != FRAME_BYTES:
            raise ValueError("Expected exactly 225 RGB8 bytes")
        if not self.session_ready:
            raise RGBError("Open external mode first")
        self._reconcile()
        if self.seq == 65535:
            raise RGBError("Frame sequence exhausted. Close and open a fresh session")
        seq = self.seq + 1
        checksum = struct.pack("<I", zlib.crc32(rgb))
        use_fast = fast and bool(self.caps.features & 4)
        self._uncertain = (seq, rgb)
        for index in range(5):
            data = rgb[48*index:48*(index+1)]
            if index == 4 and use_fast:
                reply = self.request(Op.CHUNK_COMMIT, arg=index, seq=seq, data=data + checksum,
                                     allowed=(Status.OK, Status.BUSY))
            else:
                reply = self.request(Op.CHUNK, arg=index, seq=seq, data=data)
        if not use_fast or reply.status == Status.BUSY:
            deadline = time.monotonic() + 0.75
            while True:
                reply = self.request(Op.COMMIT, seq=seq, data=checksum,
                                     allowed=(Status.OK, Status.BUSY))
                if reply.status == Status.OK:
                    break
                if time.monotonic() >= deadline:
                    raise CommandFailed(Op.COMMIT, reply)
                time.sleep(0.002)
        if reply.accepted != seq:
            raise RGBError("Firmware did not acknowledge the committed sequence")
        self.frame, self.seq, self._uncertain = rgb, seq, None
        return reply

    def set_key(self, bank, index, rgb):
        if not 0 <= bank < BANKS or not 0 <= index < SLOTS:
            raise ValueError("LED bank must be 0–4 and index 0–14")
        if isinstance(rgb, int):
            raise ValueError("Expected one RGB triplet")
        color = bytes(rgb)
        if len(color) != 3:
            raise ValueError("Expected one RGB triplet")
        self._reconcile()
        frame = bytearray(self.frame)
        offset = 3 * (bank * SLOTS + index)
        frame[offset:offset+3] = color
        return self.set_frame(frame)

    def close(self, *, restore=True):
        try:
            if restore and self.token:
                self.native()
        finally:
            self.transport.close()
