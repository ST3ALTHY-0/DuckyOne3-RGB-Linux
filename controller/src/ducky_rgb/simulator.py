"""In-process V4 device with explicit timing and transport fault controls."""
from collections import deque
import struct
import threading
import time
import zlib

from .protocol import FRAME_BYTES, PREFIX, Op, Status
from .transport import Endpoint

SIMULATOR = Endpoint(b"demo", "Simulated One 3 SF", simulator=True)


class SimulatedDevice:
    def __init__(self, clock=time.monotonic, *, scan_period=0.0033):
        self.clock, self.scan_period = clock, scan_period
        self._online = True
        self.lock = threading.RLock()
        self.token = self.closed = self.lease = self.mode = 0
        self.accepted = self.displayed = self.revision = self.displayed_revision = 0
        self.frame = bytes(FRAME_BYTES)
        self.brightness = 65535
        self.overlays = self.initial_overlays = 0
        self.chunks = {}
        self.intent = None
        self.activity = self.opened = self.stage_time = self.due = 0.0

    @property
    def online(self):
        return self._online

    @online.setter
    def online(self, value):
        # Cable removal invalidates firmware ownership and pending USB reports.
        with self.lock:
            if self._online and not value:
                self.revoke()
            self._online = value

    def revoke(self):
        if self.token:
            self.closed = self.token
        self.token = self.mode = self.accepted = self.displayed = 0
        self.chunks.clear()
        self.intent = None

    def tick(self, now):
        if self.token and ((self.lease and now-self.activity >= self.lease/1000)
                           or (self.mode == 1 and now-self.opened >= 2)):
            self.revoke()
        if self.chunks and now-self.stage_time >= 1:
            self.chunks.clear()
            self.intent = None
        if self.mode >= 2 and now >= self.due:
            self.mode = 3
            self.displayed, self.displayed_revision = self.accepted, self.revision

    def changed(self, now):
        self.revision = (self.revision % 0xffffffff) + 1
        self.due = now+self.scan_period

    def command(self, p, now):
        if len(p) != 64:
            return Status.BAD_LENGTH
        major, op, arg, token, seq = struct.unpack_from("<BBBIH", p, 5)
        if major != 1 and not (major == 0 and op == Op.CAPS):
            return Status.BAD_VERSION
        if op not in set(Op):
            return Status.BAD_OPCODE
        end = 14
        if op == Op.MODE and arg == 1:
            end = 17
        elif op in (Op.CHUNK, Op.CHUNK_COMMIT):
            if arg > 4 or (op == Op.CHUNK_COMMIT and arg != 4):
                return Status.BAD_ARGUMENT
            end = 51 if op == Op.CHUNK_COMMIT else 47 if arg == 4 else 62
        elif op == Op.COMMIT:
            end = 18
        elif op == Op.BRIGHTNESS:
            end = 16
        frame_op = op in (Op.CHUNK, Op.CHUNK_COMMIT, Op.COMMIT, Op.ABORT)
        if (bool(seq) != frame_op or not any(p[62:]) or any(p[end:62])
                or (op == Op.CAPS and token) or (op == Op.MODE and arg > 1)
                or (arg and op not in (Op.MODE, Op.CHUNK, Op.CHUNK_COMMIT, Op.OVERLAYS))):
            return Status.BAD_ARGUMENT
        if op == Op.CAPS or (op == Op.STATUS and not token):
            return Status.OK
        if op == Op.MODE:
            if not arg:
                if token and token == self.token:
                    self.revoke()
                    return Status.OK
                return Status.OK if token and not self.token and token == self.closed else Status.WRONG_SESSION
            lease, overlays = struct.unpack_from("<HB", p, 14)
            if not token or (lease and not 1000 <= lease <= 60000):
                return Status.BAD_ARGUMENT
            if overlays > 15:
                return Status.UNSUPPORTED
            if self.token == token:
                return Status.OK if (lease, overlays) == (self.lease, self.initial_overlays) else Status.CONFLICT
            if self.token:
                return Status.BUSY
            if token == self.closed:
                return Status.WRONG_SESSION
            self.token, self.lease, self.mode, self.opened = token, lease, 1, now
            self.brightness, self.overlays, self.initial_overlays = 65535, overlays, overlays
            return Status.OK
        if token != self.token or not token:
            return Status.WRONG_SESSION
        if op in (Op.STATUS, Op.KEEPALIVE):
            return Status.OK
        if op == Op.BRIGHTNESS:
            brightness = struct.unpack_from("<H", p, 14)[0]
            if self.brightness != brightness:
                self.brightness = brightness
                self.changed(now)
            return Status.OK
        if op == Op.OVERLAYS:
            if arg > 15:
                return Status.UNSUPPORTED
            if self.overlays != arg:
                self.overlays = arg
                self.changed(now)
            return Status.OK
        if seq not in (self.accepted, self.accepted+1):
            return Status.STALE_SEQUENCE
        if op == Op.ABORT:
            if seq == self.accepted:
                return Status.CONFLICT
            self.chunks.clear()
            self.intent = None
            return Status.OK
        crc = struct.unpack_from("<I", p, 14 if op == Op.COMMIT else 47)[0] if op in (Op.COMMIT, Op.CHUNK_COMMIT) else None
        if op != Op.COMMIT:
            chunk = p[14:47 if arg == 4 else 62]
            if seq == self.accepted:
                valid = chunk == self.frame[48*arg:48*(arg+1)]
                return Status.OK if valid and (crc is None or crc == zlib.crc32(self.frame)) else Status.CONFLICT
            if arg in self.chunks and self.chunks[arg] != chunk:
                return Status.CONFLICT
            if crc is not None and self.intent is not None and crc != self.intent:
                return Status.CONFLICT
            self.chunks[arg] = chunk
            self.stage_time = now
            if crc is not None:
                self.intent = crc
            crc = self.intent
        if crc is None:
            return Status.OK
        if seq == self.accepted:
            return Status.OK if crc == zlib.crc32(self.frame) else Status.CONFLICT
        if self.intent is not None and crc != self.intent:
            return Status.CONFLICT
        if len(self.chunks) != 5:
            return Status.INCOMPLETE
        if self.displayed != self.accepted:
            return Status.BUSY
        frame = b"".join(self.chunks[i] for i in range(5))
        if zlib.crc32(frame) != crc:
            self.intent = None
            return Status.BAD_CRC
        self.frame, self.accepted = frame, seq
        self.chunks.clear()
        self.intent = None
        if self.mode == 1:
            self.mode = 2
        self.changed(now)
        return Status.OK

    def exchange(self, payload):
        with self.lock:
            if not self.online:
                raise OSError("Simulator disconnected")
            return self._exchange(payload)

    def _exchange(self, payload):
        now = self.clock()
        self.tick(now)
        if len(payload) < 5 or payload[:5] != PREFIX:
            return None
        status = self.command(payload, now)
        p = payload.ljust(64, b"\0")
        token = struct.unpack_from("<I", p, 8)[0]
        owns = token and token == self.token
        if owns and status == Status.OK:
            self.activity = now
        reply = bytearray(64)
        reply[:6] = PREFIX + b"\x01"
        reply[6:14] = bytes((p[6] | 0x80, status)) + p[8:14]
        reply[14] = self.mode
        if owns:
            coverage = sum(1 << i for i in self.chunks)
            struct.pack_into("<B4H2IHB", reply, 15, coverage, self.accepted+1 if coverage else 0,
                             self.accepted, self.accepted if self.mode >= 2 else 0, self.displayed,
                             self.revision, self.displayed_revision, self.brightness, self.overlays)
            struct.pack_into("<H", reply, 50, self.lease)
        struct.pack_into("<BII6B", reply, 35, 15, 31, 0x01160001, 75, 5, 15, 16, 5, 64)
        reply[52:54] = bytes((1, p[7]))
        reply[62:] = p[62:64]
        return bytes(reply)


class SimulatorBackend:
    def __init__(self, *, latency=0.001):
        self.device = SimulatedDevice()
        self.latency = latency
        self.drop_next = 0

    def enumerate(self):
        return [SIMULATOR] if self.device.online else []

    def open(self, endpoint):
        if endpoint != SIMULATOR or not self.device.online:
            raise OSError("Simulator disconnected")
        return SimulatorTransport(self)


class SimulatorTransport:
    def __init__(self, backend):
        self.backend = backend
        self.responses = deque()
        self.closed = threading.Event()

    def check(self):
        if self.closed.is_set() or not self.backend.device.online:
            raise OSError("Simulator disconnected")

    def write(self, data):
        self.check()
        reply = self.backend.device.exchange(data)
        if self.backend.drop_next:
            self.backend.drop_next -= 1
        elif reply:
            self.responses.append((time.monotonic()+self.backend.latency, reply))

    def read(self, timeout):
        self.check()
        remaining = self.responses[0][0]-time.monotonic() if self.responses else timeout+1
        self.closed.wait(min(timeout, max(0, remaining)))
        self.check()
        if self.responses and self.responses[0][0] <= time.monotonic():
            return self.responses.popleft()[1]
        raise TimeoutError("Simulated HID input timed out")

    def close(self):
        self.closed.set()
        self.responses.clear()
