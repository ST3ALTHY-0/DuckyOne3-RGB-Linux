"""Single-owner HID worker with replaceable frame mailbox and lease renewal."""
from dataclasses import dataclass, replace
import time
from threading import Condition, Thread

from .protocol import CommandFailed, ConnectionLost, RGBController, RGBError, Status, UnsupportedProtocol


@dataclass(frozen=True)
class Output:
    data: bytes
    brightness: int
    overlays: int = 0
    fast: bool = True


@dataclass(frozen=True)
class Metrics:
    submitted: int = 0
    accepted: int = 0
    displayed: int = 0
    dropped: int = 0
    timeouts: int = 0
    retries: int = 0
    latency_ms: float = 0
    sequence: int = 0
    mode: int = 0


class DeviceWorker:
    def __init__(self, backends, publish, *, lease_ms=5000):
        self.backends = backends
        self.publish = publish
        self.lease_ms = lease_ms
        self.cv = Condition()
        self.endpoint = None
        self.enabled = False
        self.output = None
        self.pending = False
        self.stopping = False
        self.reconnect = True
        self.metrics = Metrics()
        self.completed_timeouts = self.completed_retries = 0
        self.thread = Thread(target=self.run, name="ducky-hid", daemon=True)
        self.thread.start()

    def select(self, endpoint, *, enabled=False):
        with self.cv:
            self.endpoint, self.enabled = endpoint, enabled
            self.cv.notify()

    def submit(self, output):
        with self.cv:
            if output != self.output:
                if self.pending and self.enabled and self.endpoint is not None:
                    self.metrics = replace(self.metrics, dropped=self.metrics.dropped+1)
                self.output, self.pending = output, True
                self.cv.notify()

    def close(self, timeout=4):
        with self.cv:
            self.stopping = True
            self.cv.notify()
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def update(self, **values):
        with self.cv:
            self.metrics = replace(self.metrics, **values)
            metrics = self.metrics
        self.publish("metrics", metrics)

    def run(self):
        client = selected = caps = None
        sent = None
        next_scan = retry = keepalive = 0.0
        endpoints = []
        try:
            while True:
                with self.cv:
                    if self.stopping:
                        break
                    endpoint, enabled, output = self.endpoint, self.enabled, self.output
                now = time.monotonic()
                if now >= next_scan:
                    detected = []
                    for backend in self.backends.values():
                        try:
                            detected.extend(backend.enumerate())
                        except (OSError, ImportError, RuntimeError) as exc:
                            self.publish("notice", f"Device discovery failed: {exc}")
                    if detected != endpoints or not next_scan:
                        if selected is not None and selected not in detected and client is not None:
                            self.release(client)
                            client = sent = None
                            retry = now if self.reconnect else float("inf")
                            self.publish("status", "Disconnected • waiting for the selected vendor collection")
                        if self.reconnect and selected is not None and selected in detected and selected not in endpoints:
                            retry = now
                        endpoints = detected
                        self.publish("devices", endpoints)
                    next_scan = now+1.25
                if selected != endpoint:
                    self.release(client)
                    client = sent = caps = None
                    selected, retry = endpoint, 0
                    if selected is None:
                        self.publish("status", "Disconnected")
                if selected is not None and now >= retry:
                    try:
                        if client is None:
                            if selected not in endpoints:
                                raise ConnectionLost("Waiting for the selected vendor collection")
                            self.publish("status", "Negotiating V4")
                            transport = self.backends[selected.simulator].open(selected)
                            client = RGBController(transport, timeout=.14, retries=2)
                            caps = client.capabilities()
                            self.publish("caps", (selected, caps))
                            self.publish("status", "Connected • native lighting" if caps.mode == 0
                                         else "Connected • another session owns lighting")
                        if not enabled and client.token:
                            client.native()
                            sent = None
                            self.update(mode=0, sequence=0)
                            self.publish("status", "Connected • native lighting")
                        if enabled and output is not None:
                            if not client.token or client.seq == 65535:
                                if client.token:
                                    client.native()
                                client.external(lease_ms=self.lease_ms, overlays=output.overlays & caps.supported_overlays)
                                sent = None
                            if sent != output:
                                with self.cv:
                                    if output == self.output:
                                        self.pending = False
                                begin = time.monotonic()
                                if sent is None or sent.brightness != output.brightness:
                                    client.brightness(output.brightness)
                                if sent is None or sent.overlays != output.overlays:
                                    client.overlays(output.overlays & caps.supported_overlays)
                                new_frame = sent is None or sent.data != output.data
                                if new_frame:
                                    self.update(submitted=self.metrics.submitted+1)
                                    accepted = client.set_frame(output.data, fast=output.fast)
                                    self.update(accepted=self.metrics.accepted+1, sequence=accepted.accepted)
                                else:
                                    accepted = client.status()
                                ready = client.wait_displayed(revision=accepted.revision)
                                self.update(displayed=self.metrics.displayed+int(new_frame), mode=ready.mode,
                                            latency_ms=(time.monotonic()-begin)*1000)
                                sent = output
                                self.publish("displayed", (selected, output))
                                keepalive = time.monotonic()+client.lease_ms/3000
                                self.publish("status", "Connected • external lighting")
                            elif now >= keepalive:
                                client.keepalive()
                                keepalive = now+client.lease_ms/3000
                    except PermissionError as exc:
                        self.publish("status", f"Permission denied • {exc}")
                        self.release(client)
                        client = None
                        retry = now+3
                    except UnsupportedProtocol as exc:
                        self.publish("status", f"Unsupported firmware • {exc}")
                        self.release(client)
                        client = None
                        retry = now+1.5 if self.reconnect and caps and isinstance(exc.__cause__, TimeoutError) else float("inf")
                    except (RGBError, OSError) as exc:
                        busy = isinstance(exc, CommandFailed) and exc.reply.status in (Status.BUSY, Status.WRONG_SESSION)
                        self.publish("status", f"{'Session unavailable' if busy else 'Recovering'} • {exc}")
                        self.release(client)
                        client = sent = None
                        retry = time.monotonic()+1.5 if self.reconnect else float("inf")
                totals = (self.completed_timeouts+(client.timeout_count if client else 0),
                          self.completed_retries+(client.retry_count if client else 0))
                if totals != (self.metrics.timeouts, self.metrics.retries):
                    self.update(timeouts=totals[0], retries=totals[1])
                with self.cv:
                    if not self.stopping and self.endpoint == endpoint and self.enabled == enabled and self.output == output:
                        self.cv.wait(.08)
        finally:
            self.release(client)

    def release(self, client):
        if client:
            try:
                client.close()
            except (RGBError, OSError) as exc:
                self.publish("notice", f"Native restoration unconfirmed • lease fallback ({exc})")
            finally:
                self.completed_timeouts += client.timeout_count
                self.completed_retries += client.retry_count
