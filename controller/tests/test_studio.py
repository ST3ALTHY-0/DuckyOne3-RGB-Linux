import os
import struct
import time

import numpy as np
import pytest

from ducky_rgb.devices import Assignment, DUCKY, mapping_json, validate_mapping
from ducky_rgb.effects import EFFECTS
from ducky_rgb.engine import BLENDS, Layer, Renderer, composite
from ducky_rgb.protocol import CommandFailed, DESCRIPTOR, Op, RGBController, Status, UnsupportedProtocol, packet
from ducky_rgb.simulator import SIMULATOR, SimulatorBackend
from ducky_rgb.storage import Profile, Storage, validate_profile
from ducky_rgb.transport import HIDBackend, HIDTransport, vendor_descriptor
from ducky_rgb.worker import DeviceWorker, Output


def ready(predicate, timeout=3, idle=None):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        if idle:
            idle()
        if predicate():
            return
        time.sleep(.01)
    assert predicate()


def test_hid_frames():
    class Wire:
        def write(self, data):
            assert data == b"\0"+bytes(range(64))
            return 65

        def read(self, maximum, timeout):
            assert maximum == 65 and timeout > 0
            return self.reply

    wire = Wire()
    transport = HIDTransport(wire)
    transport.write(bytes(range(64)))
    for prefix in (b"", b"\0"):
        wire.reply = prefix+bytes(range(64))
        assert transport.read(.005) == bytes(range(64))
    wire.reply = b""
    with pytest.raises(TimeoutError):
        transport.read(.005)


def test_hid_reconstructed_descriptor():
    # Same top-level collection/report sizes with compact logical metadata omitted.
    assert vendor_descriptor(bytes.fromhex("06 00 ff 09 01 a1 01 75 08 95 40 81 00 91 00 c0"))
    assert not vendor_descriptor(bytes.fromhex("06 00 ff 09 01 a1 01 85 01 75 08 95 40 81 00 91 00 c0"))
    assert not vendor_descriptor(DESCRIPTOR.replace(b"\x95\x40", b"\x95\x08"))
    assert not vendor_descriptor(b"\xff")


def test_filters_before_open():
    entries = [{"vendor_id": 0x3233, "product_id": 0x5311, "path": b"vendor",
                "usage_page": 0xff00, "usage": 1, "interface_number": 0}]
    entries.extend([dict(entries[0], path=b"keys", usage_page=1), dict(entries[0], path=b"boot", product_id=0x5310),
                    dict(entries[0], path=b"unknown", usage_page=0),
                    dict(entries[0], path=b"wrong-interface", interface_number=3)])
    class Binding:
        def enumerate(self, vid, pid):
            assert (vid, pid) == (0x3233, 0x5311)
            return entries

        def device(self):
            return self

        def open_path(self, path):
            assert path == b"vendor"

        def get_report_descriptor(self):
            return DESCRIPTOR

        def close(self):
            pass

    backend = HIDBackend(Binding())
    assert [e.path for e in backend.enumerate()] == [b"vendor"]
    backend.open(backend.enumerate()[0]).close()


@pytest.mark.parametrize("fast", [False, True])
def test_session_and_retry(fast):
    backend = SimulatorBackend(latency=0)
    client = RGBController(backend.open(SIMULATOR), timeout=.015)
    competitor = RGBController(backend.open(SIMULATOR), timeout=.015)
    assert client.capabilities().geometry == (75, 5, 15, 16, 5, 64)
    client.external(lease_ms=1000, overlays=2)
    with pytest.raises(CommandFailed) as error:
        competitor.external()
    assert error.value.reply.status == Status.BUSY
    backend.drop_next = 1
    assert client.set_frame(bytes(range(225)), fast=fast).accepted == 1
    assert client.wait_displayed().displayed == 1
    assert client.brightness(123).brightness == 123
    assert client.overlays(5).overlays == 5
    client.seq = 65535
    with pytest.raises(RuntimeError, match="exhausted"):
        client.set_frame(bytes(225))
    client.close()
    competitor.close()


def test_protocol_edges():
    sim = SimulatorBackend(latency=0).device
    clock = iter([0., 0., 0., 0., 2.])
    sim.clock = lambda: next(clock)
    token = 223
    assert sim.exchange(packet(Op.MODE, arg=1, token=token, data=struct.pack("<HB", 1000, 0), tag=1))[7] == 0
    assert sim.exchange(packet(Op.CHUNK, arg=5, token=token, seq=1, tag=2))[7] == Status.BAD_ARGUMENT
    assert sim.exchange(packet(Op.COMMIT, token=token, seq=1, tag=3))[7] == Status.INCOMPLETE
    assert sim.exchange(packet(Op.STATUS, token=token, tag=4))[7] == Status.OK
    assert sim.exchange(packet(Op.KEEPALIVE, token=token, tag=5))[7] == Status.WRONG_SESSION

    class Silent:
        def write(self, report):
            assert report[6] == Op.CAPS

        def read(self, timeout):
            raise TimeoutError

    with pytest.raises(UnsupportedProtocol):
        RGBController(Silent(), retries=1).capabilities()


@pytest.mark.parametrize("name", EFFECTS)
def test_effect_determinism(name):
    renderer = Renderer()
    layer = Layer(name, name)
    a, wire = renderer.render([layer], 1.1, [("A", .2, True, 4)])
    assert len(a) == len(DUCKY.keys) and len(wire) == DUCKY.slots * 3
    assert (a, wire) == renderer.render([layer], 1.1, [("A", .2, True, 4)])


@pytest.mark.parametrize("blend", BLENDS)
def test_blends(blend):
    base = np.array([[.2, .45, .9]])
    top = np.array([[1., .2, .4]])
    assert np.array_equal(composite(base, top, blend, 0), base)
    assert np.all((composite(base, top, blend, 1) >= 0) & (composite(base, top, blend, 1) <= 1))


def test_map_and_paint():
    mapping = {0: Assignment(("Q", "W"), True), 1: Assignment((), True), 2: Assignment(("Q",), False)}
    assert validate_mapping(mapping_json(mapping)) == mapping
    preview, wire = Renderer(mapping=mapping).render(
        [Layer("paint", "Paint", paint={"Q": "#ff7f00"}, mask=["Q"])], 2, preview_brightness=.5)
    assert preview["Q"] == [128, 64, 0]
    assert wire[:9] == bytes((255, 127, 0))+bytes(6)
    assert len(DUCKY.keys) == 67


def test_profiles(tmp_path):
    storage = Storage(tmp_path/"config", tmp_path/"data")
    profile = Profile("Portable")
    storage.save_profiles([profile])
    assert storage.load_profiles() == [profile]
    assert validate_profile({**profile.encode(), "version": 1}) == profile
    with pytest.raises(ValueError):
        validate_profile({**profile.encode(), "fps": float("nan")})
    with pytest.raises(ValueError):
        validate_profile({**profile.encode(), "layers": [{"effect": "paint", "paint": {"invalid": "#000000"}}]})


def test_worker_coalesces_reconnects_and_restores():
    backend = SimulatorBackend()
    events = []
    worker = DeviceWorker({True: backend}, lambda tag, data: events.append((tag, data)))
    try:
        worker.select(SIMULATOR)
        ready(lambda: any(tag == "caps" for tag, _ in events))
        worker.select(SIMULATOR, enabled=True)
        for i in range(50):
            worker.submit(Output(bytes([i])*225, 12000))
        ready(lambda: backend.device.displayed > 0 and backend.device.frame == bytes([49])*225)
        backend.device.online = False
        worker.submit(Output(bytes([51])*225, 12000))
        ready(lambda: any(tag == "status" and "Recovering" in data for tag, data in events))
        backend.device.online = True
        ready(lambda: backend.device.frame == bytes([51])*225, timeout=5)
    finally:
        assert worker.close()
    assert backend.device.mode == 0 and backend.device.token == 0


def test_gui_simulator(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ducky_rgb.platforms import Startup
    from ducky_rgb.window import MainWindow

    app = QApplication.instance() or QApplication([])
    backend = SimulatorBackend()
    window = MainWindow(Storage(tmp_path/"config", tmp_path/"data"), {True: backend},
                        Startup(["ducky-rgb"]), auto_simulate=True)
    window.show()
    try:
        ready(lambda: window.caps is not None, idle=app.processEvents)
        window.add_layer()
        window.canvas.select({"W", "A"})
        window.paint_keys(window.canvas.selected)
        assert window.profile.layers[-1].effect == "paint"
        window.undo()
        assert window.profile.layers[-1].effect != "paint"
        window.redo()
        window.apply()
        ready(lambda: backend.device.displayed > 0, idle=app.processEvents)
        window.start_calibration()
        ready(lambda: window.last_displayed_output == window.override, idle=app.processEvents)
        window.canvas.select({"W"})
        window.assign(False)
        assert window.mapping[0] == Assignment(("W",), False)
        window.native()
        ready(lambda: backend.device.token == 0, idle=app.processEvents)
        original = window.profiles[0].encode()
        window.add_builtin_profile(window.profiles[0])
        assert window.profile.name == "Spectrum (2)"
        assert window.profiles[0].encode() == original
    finally:
        window.close()
        assert window.worker.close()


def test_reactive_intensity_and_gamma():
    renderer = Renderer(mapping={7: Assignment(("A",), True)})
    layer = Layer("fade", params={"Color": "#ff0000", "Fade seconds": 1.0})
    _, first = renderer.render([layer], 4., [("A", .5, False, 1)], gamma=2)
    _, later = renderer.render([layer], 4., [("A", 1.5, False, 1)], gamma=2)
    assert first[21:24] == bytes((64, 0, 0))
    assert later == bytes(225)


def test_platform_capabilities_and_xdg_startup(tmp_path, monkeypatch):
    from ducky_rgb import platforms
    monkeypatch.setattr(platforms.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    startup = platforms.Startup(["/opt/space path/python", "-m", "ducky_rgb"])
    assert not startup.enabled()
    startup.set(True)
    assert startup.enabled()
    assert 'Exec="/opt/space path/python" "-m" "ducky_rgb"' in startup.path().read_text()
    startup.set(False)
    assert not startup.enabled()
    caps = platforms.capability_report()
    assert caps["Reactive input"].available
    assert not caps["Screen capture"].available and not caps["Audio capture"].available


def test_gradient_stop_validation():
    row = Profile(layers=[Layer("multicolor", params={"Palette": ["#000000", "#ffffff"],
                                                     "Stop positions": [0.1, 0.9]})])
    assert validate_profile(row.encode()) == row
    row.layers[0].params["Stop positions"] = [.2]
    with pytest.raises(ValueError, match="stop count"):
        validate_profile(row.encode())


def test_linux_hidraw_recovers_missing_hidapi_metadata(tmp_path):
    from ducky_rgb.linux_hidraw import LinuxVendorBackend
    for name, descriptor in [("hidraw6", DESCRIPTOR), ("hidraw7", bytes.fromhex("05010906a101c0"))]:
        path = tmp_path/name/"device"
        path.mkdir(parents=True)
        (path/"uevent").write_text("HID_ID=0003:00003233:00005311\n")
        (path/"report_descriptor").write_bytes(descriptor)
    backend = LinuxVendorBackend(sysfs=tmp_path, dev=tmp_path/"dev")
    device, = backend.enumerate()
    assert device.path.endswith(b"/hidraw6") and device.backend == "Linux hidraw"
    with pytest.raises(RuntimeError, match="cannot access its HID device node"):
        backend.open(device)


def test_builtin_profiles_render_without_calibration():
    from ducky_rgb.storage import examples

    profiles = examples()
    renderer = Renderer()
    assert len(profiles) >= 11
    assert len({profile.name for profile in profiles}) == len(profiles)
    frames = set()
    for profile in profiles:
        assert validate_profile(profile.encode()) == profile
        _, frame = renderer.render(profile.layers, 1.25, gamma=profile.gamma)
        assert len(frame) == 225 and all(max(frame[i:i+3]) for i in range(0, 225, 3))
        frames.add(frame)
    assert len(frames) == len(profiles)
