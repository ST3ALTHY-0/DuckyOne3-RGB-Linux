# Native packaging

In an isolated build environment on the target operating system, install `.[bundle]` and run `python packaging/build.py --smoke` from the controller directory. The script uses PyInstaller’s native onedir layout. It produces a Linux tarball, Windows portable ZIP or macOS app and DMG. Linux builds should use the oldest glibc baseline you intend to support. No AppImage is configured. Do not cross-build Windows or macOS bundles using Linux.

- **Windows installer** — run Inno Setup 6 against `windows/studio.iss` after building the native bundle. Pass `/DBundleDir=...` when using a nondefault output path. The installer is per user and provides uninstallation, Start menu shortcuts and an optional desktop shortcut.
- **Linux desktop entry** — copy the desktop file to the user's XDG applications directory, install `assets/studio.png` in the hicolor 256×256 apps icon directory under the name `ducky-rgb-studio.png`, and ensure the entry's executable resolves outside a shell. To launch a virtual environment or portable build, set Exec to that executable's absolute path. Install only the relevant permission rule in the OS rule directory and replug. No system daemon is involved.
- **macOS** — build on each target architecture using a matching Python and compatible Qt/HIDAPI wheels. The DMG is unsigned and unnotarized unless the publisher signs the inner product with an appropriate Developer ID, notarizes and staples the distributable. Review all embedded Qt and HID libraries before release. The configured native workflow uses the runner's architecture.
- **Wheel** — `python -m pip wheel --no-deps .` creates an independent package. Install it in a clean environment with its declared dependencies and use the entry point.

Consult [third-party notices](THIRD-PARTY.md) before publishing. The build workflow uploads CI artifacts and does not publish a release or program a keyboard.
