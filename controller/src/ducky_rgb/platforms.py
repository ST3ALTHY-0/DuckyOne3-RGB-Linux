"""Desktop capabilities and per-user launch registration."""
from dataclasses import dataclass
from pathlib import Path
import os
import plistlib
import subprocess
import sys


@dataclass(frozen=True)
class Capability:
    available: bool
    description: str


def capability_report():
    return {
        "Reactive input": Capability(True, "Focused keyboard preview only. Global input capture is disabled."),
        "Audio capture": Capability(False, "No opt-in audio capture adapter is installed."),
        "Screen capture": Capability(False, "No opt-in screen capture adapter is installed."),
        "Active application": Capability(False, "No active application adapter is installed."),
        "Power events": Capability(False, "Transport failures and session leases handle sleep recovery."),
        "Hotplug": Capability(True, "HIDAPI enumeration, polled in the background."),
    }


class Startup:
    def __init__(self, executable):
        self.argv = executable
        self.token = "DuckyRGBStudio"

    @property
    def available(self):
        return sys.platform.startswith("linux") or sys.platform in ("win32", "darwin")

    def path(self):
        if sys.platform == "darwin":
            return Path.home() / "Library" / "LaunchAgents" / "org.duckyrgb.studio.plist"
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home()/".config") / "autostart" / "ducky-rgb-studio.desktop"

    def enabled(self):
        if sys.platform != "win32":
            return self.available and self.path().exists()
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, self.token)
                return True
        except FileNotFoundError:
            return False

    def set(self, enabled):
        if sys.platform == "win32":
            import winreg
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                                     0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, self.token, 0, winreg.REG_SZ, subprocess.list2cmdline(self.argv))
                elif self.enabled():
                    winreg.DeleteValue(key, self.token)
        elif self.available:
            path = self.path()
            if not enabled:
                path.unlink(missing_ok=True)
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                path.write_bytes(plistlib.dumps({"Label": "org.duckyrgb.studio", "ProgramArguments": self.argv,
                                                 "RunAtLoad": True}))
            else:
                def desktop_quote(value):
                    value = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
                    value = value.replace("$", "\\$").replace("`", "\\`")
                    return '"' + value + '"'
                command = " ".join(map(desktop_quote, self.argv))
                path.write_text("[Desktop Entry]\nType=Application\nName=Ducky RGB Studio\n"
                                f"Exec={command}\nTerminal=false\n", encoding="utf-8")


def desktop_hid_backend(primary):
    if sys.platform.startswith("linux"):
        from .linux_hidraw import LinuxVendorBackend
        return LinuxVendorBackend(primary)
    return primary
