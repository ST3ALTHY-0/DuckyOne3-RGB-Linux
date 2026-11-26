"""Desktop entry point, dependency discovery and per-user instance lock."""
import argparse
import json
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .platforms import desktop_hid_backend
from .simulator import SimulatorBackend
from .transport import HIDBackend


def arguments(argv=None):
    parser = argparse.ArgumentParser(prog="ducky-rgb", description="Ducky RGB Studio")
    parser.add_argument("--simulate", action="store_true", help="Select the simulated keyboard without HID access")
    parser.add_argument("--list-devices", action="store_true", help="Enumerate vendor collections without opening them")
    parser.add_argument("--profile", help="Select a host profile at startup")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=app_version())
    return parser.parse_args(argv)


def app_version():
    try:
        return version("ducky-rgb-studio")
    except PackageNotFoundError:
        return "0.1.2"


def main(argv=None):
    args = arguments(argv)
    backends = {True: SimulatorBackend()}
    unavailable = None
    if not (args.simulate or args.smoke_test):
        primary = None
        try:
            primary = HIDBackend()
        except (ImportError, OSError) as exc:
            unavailable = f"HIDAPI unavailable: {exc}. Reinstall the hidapi package to use the preferred USB backend."
        if backend := desktop_hid_backend(primary):
            backends[False] = backend
    if args.list_devices:
        try:
            devices = [d for backend in backends.values() for d in backend.enumerate()]
        except (OSError, RuntimeError) as exc:
            print(f"Device enumeration failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps([{"name": d.label, "VID": f"{d.vid:04x}", "PID": f"{d.pid:04x}",
                           "interface": d.interface, "simulator": d.simulator,
                           "backend": "Simulator" if d.simulator else d.backend} for d in devices], indent=2))
        if unavailable:
            print(unavailable, file=sys.stderr)
        return 0

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .platforms import Startup
    from .storage import Storage
    from .window import MainWindow

    app = QApplication([sys.argv[0]])
    app.setApplicationName("Ducky RGB Studio")
    app.setApplicationVersion(app_version())
    app.setOrganizationName("Ducky RGB Studio")
    icon = Path(__file__).with_name("assets") / "studio.png"
    app.setWindowIcon(QIcon(str(icon)))
    temporary = tempfile.TemporaryDirectory() if args.smoke_test else None
    storage = Storage(Path(temporary.name)/"config", Path(temporary.name)/"data") if temporary else Storage()
    try:
        storage.config.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        QMessageBox.critical(None, "Ducky RGB Studio", f"Could not access settings: {exc}")
        return 1
    lock = QLockFile(str(storage.config / "studio.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "Ducky RGB Studio", "The studio is already open or its settings are locked.")
        return 1
    executable = [str(Path(sys.executable))] if getattr(sys, "frozen", False) else [
        str(Path(sys.executable)), "-m", "ducky_rgb"]
    if args.simulate:
        executable.append("--simulate")
    window = MainWindow(storage, backends, Startup(executable),
                        auto_simulate=args.simulate or args.smoke_test, profile_name=args.profile)
    if unavailable:
        window.notice(unavailable)
    window.show()
    if args.smoke_test:
        timer = QTimer(window)
        timer.setInterval(25)
        def exercise():
            if window.caps and not window.external:
                window.apply()
            if window.metrics.displayed:
                timer.stop()
                window.close()
        timer.timeout.connect(exercise)
        timer.start()
        QTimer.singleShot(8000, lambda: app.exit(2))
    try:
        return app.exec()
    finally:
        window.worker.close()
        lock.unlock()
        if temporary:
            temporary.cleanup()
