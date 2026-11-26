"""Build a native, replaceable-library PyInstaller bundle on the current OS."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "src/ducky_rgb/assets/studio.png"
NAME = "Ducky RGB Studio"


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def mac_icon(base):
    iconset = base / "Studio.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for multiplier in (1, 2):
            suffix = "@2x" if multiplier == 2 else ""
            run("sips", "-z", size*multiplier, size*multiplier, ICON, "--out",
                iconset / f"icon_{size}x{size}{suffix}.png")
    target = base / "studio.icns"
    run("iconutil", "-c", "icns", iconset, "-o", target)
    return target


def build(base, validate):
    base = base.resolve()
    base.mkdir(parents=True, exist_ok=True)
    dist = base / "native"
    windows = sys.platform == "win32"
    mac = sys.platform == "darwin"
    launcher = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
                "--name", NAME, "--distpath", dist, "--workpath", base/"work", "--specpath", base,
                "--paths", ROOT/"src", "--hidden-import", "hid",
                "--add-data", f"{ICON}:ducky_rgb/assets",
                "--add-data", f"{ROOT/'LICENSE'}:licenses",
                "--add-data", f"{ROOT/'packaging/THIRD-PARTY.md'}:licenses"]
    if windows:
        launcher += ["--icon", ROOT/"packaging/windows/studio.ico"]
    elif mac:
        launcher += ["--icon", mac_icon(base), "--osx-bundle-identifier", "org.duckyrgb.studio"]
    run(*launcher, ROOT/"src/ducky_rgb/__main__.py")
    bundle = dist / (NAME+".app" if mac else NAME)
    exe = bundle / (f"Contents/MacOS/{NAME}" if mac else NAME+(".exe" if windows else ""))
    if validate:
        run(exe, "--smoke-test", env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=20)
    if windows:
        shutil.make_archive(str(base/"DuckyRGBStudio-Windows"), "zip", dist, bundle.name)
    elif mac:
        run("hdiutil", "create", "-ov", "-format", "UDZO", "-volname", NAME,
            "-srcfolder", bundle, base/"DuckyRGBStudio-macOS.dmg")
    else:
        shutil.make_archive(str(base/"DuckyRGBStudio-Linux"), "gztar", dist, bundle.name)
    print(f"Native output: {base}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"dist")
    parser.add_argument("--smoke", action="store_true")
    options = parser.parse_args()
    build(options.output, options.smoke)
