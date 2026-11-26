# Ducky RGB Studio

A desktop lighting editor for the Ducky One 3 SF RGB running the repository’s V4 firmware. Edit layers, paint on the ANSI keyboard preview, manage portable host profiles, calibrate physical LEDs, and inspect accepted frames and firmware scanout acknowledgments. The simulator requires no attached keyboard, USB access, or administrator permissions.

## Install and start

Use Python 3.11–3.14 and a virtual environment. Run the following from the controller source directory.

| System | Create environment | Install | Start simulator |
|---|---|---|---|
| Gentoo and other Linux distributions | `python3 -m venv .venv` | `.venv/bin/python -m pip install .` | `.venv/bin/ducky-rgb --simulate` |
| Windows 10/11 | `py -3.13 -m venv .venv` | `.venv\Scripts\python.exe -m pip install .` | `.venv\Scripts\ducky-rgb.exe --simulate` |
| macOS | `python3 -m venv .venv` | `.venv/bin/python -m pip install .` | `.venv/bin/ducky-rgb --simulate` |

After installation, launch `ducky-rgb` through the environment or the application bundle. `python -m ducky_rgb` works in the same environment. `--list-devices` enumerates vendor collections without opening them. `--profile "Midnight"` selects a host profile. `--simulate` suppresses HIDAPI enumeration. Select the simulator and use **Apply to simulator** to exercise the same transaction worker used for USB.

### Gentoo and other Linux distributions

The application works with standard Qt 6 platform plugins selected by the desktop environment. Local launch verification used the headless Qt platform. Native Wayland and X11 interaction remain to be tested. For Gentoo use a Python installation with venv/ensurepip support. Prefer the PyPI wheels in a virtual environment. A compatible system Qt/PySide6 installation can be reused with `--system-site-packages` if PyPI wheels are unavailable for the architecture. Install Qt platform dependencies required by the distro for Wayland or XCB. Distro Python, Qt and HIDAPI package names vary. The controller does not depend on systemd or a specific desktop.

Install either the bundled seat ACL rule or the group alternative through your usual administrative process and replug the keyboard. The rules match only `3233:5311`, USB interface `00`. Do not install both unless both access policies are intentional. For the group rule, create `ducky-rgb` and add the intended users, then log out and back in. On OpenRC use the group rule if the session does not receive uaccess ACLs. Launch the app as your normal user. See [permission and desktop files](packaging/linux).

### Windows and macOS

Use the standard HID class driver on Windows. Driver replacement through Zadig and administrator rights are unnecessary. On macOS, use a Python distribution that matches the machine’s architecture. The current reactive backend sees only the focused preview, so the app does not request Input Monitoring, screen recording, or microphone permissions. Physical USB behavior on Windows and macOS remains unverified. Native bundle and installer builds for those platforms are configured in CI and have yet to be run.

## Studio workflow

1. Select the vendor interface or simulator. The worker negotiates V4 capability discovery before enabling **Apply to keyboard**. The handshake checks version and geometry. The firmware does not provide flash hash attestation. Use **Native lighting** to close the application’s own session.
2. Select a host profile and add layers. Layers render bottom to top. Adjust opacity, speed, palette and blend mode in the effect panel. Palette fields accept hex colors in order and provide editable swatches. Supported gradients accept normalized stop positions, or use evenly spaced stops. Select keys in the keyboard canvas and apply them as a mask, or paint into a per-key layer. Ctrl/Command toggles keys, Shift selects a range, and dragging selects a box. Built-in and saved groups are in the selection menu. Standard Undo/Redo shortcuts restore the selected profile’s previous edits.
3. For physical per-key control, calibrate the installed keyboard. Start a slot test, identify the lit key or keys, select them in Studio, and record the assignment. Mark unused slots explicitly. Review or change any prior assignment with the slot selector. Simulator assignments are provisional. Shared slots cannot display independent colors for their member keys. Calibrated assignments are stored separately from profiles.
4. Use Device settings for brightness, gamma, FPS, fast/standard transactions, negotiated overlays, and the next session’s lease duration. Automatic application is off initially. An explicit selection can opt in to applying the last profile at startup when an unambiguous matching vendor path is present and V4 negotiation succeeds. Enable optional firmware overlays only if you want stock firmware to replace affected colors. Diagnostics shows simulated or actual host timing, firmware acceptance, and scanout acknowledgments. A scanout acknowledgement indicates page selection rather than emitted light. Tests require explicit action. Stop restores the profile or native mode as appropriate.

Profiles and machine settings live in platformdirs locations. JSON import is bounded and validated. Profiles contain no paths, device serials, executable content, or raw input events. The application sends no telemetry. Focused reactive input is opt-in, holds only a key's latest state and capped transient count, and remains in memory.

## Validation and limitations

The exact V4 image in the parent project has been physically tested on one keyboard for keyboard input, capability discovery, native restoration, static colors, individual slots, full frames and animations. That evidence predates this desktop application. Controller transport and GUI tests use mocks and simulation. No controller hardware tests or firmware operations are required or performed during development. The native CI workflow is configured for Linux, Windows and macOS. It must run on those runners before claiming successful builds or tests there.

The visual layout is the US ANSI 67-key diagram from Ducky’s One 3 SF manual. The firmware presents 75 slots. No verified physical slot map ships with Studio. Unmapped spatial effects use nominal bank/index positions, with per-key edits kept in preview until mapped. ISO layouts, global reactive hooks, audio/screen capture, active-application profiles, network services, and native suspend notifications are currently unavailable. Sleep and reconnect rely on transport rediscovery and the firmware session lease. Reconnection targets the same HID path and requires manual reselection if the OS changes it. No physical Windows or macOS compatibility, sustained keyboard frame rate, suspend behavior, complete overlays, or independent firmware recovery is claimed.

## Development and packaging

From this directory run `python -m pip install -e ".[test]"` and `python -m pytest`. Run the parent repository regression suite from its root. See [architecture and formats](docs/architecture.md) and [packaging instructions](packaging/README.md). Firmware, bootloader and recovery utilities are separate from Studio. No firmware binary is distributed with it.

Licensed [GPL-3.0-only](LICENSE). Independent of Ducky and Nuvoton.

## Local performance evidence

On the Gentoo development host, 2,000 three-layer renderer samples took 0.397 ms median and 0.828 ms p95. A synchronous 120-frame simulator run at 1 ms modeled response latency took 10.41 ms per standard transaction and 9.32 ms with the fast final-chunk commit, including scanout acknowledgment (96.1 and 107.3 frames/s respectively). These are host/simulator measurements. USB scheduling, actual scanout and input performance on a keyboard were outside this test.

The local controller suite passed **59 tests**, including the Qt offscreen simulator. The wheel was installed outside the repository and passed a simulator launch and frame-acknowledgment smoke test. The native Linux x86-64 bundle passed the same offscreen smoke test. CI defines Windows, Linux and macOS tests and native build jobs. Windows and macOS artifacts have not been produced here.

In a terminal, use `python -m ducky_rgb --list-devices` if the installed Windows GUI entry point has no console output.

If Apply only updates the preview, check the selected device. **Apply to simulator** never sends to USB. Select the physical Ducky and wait for firmware negotiation. On Linux, Studio can verify the vendor descriptor using sysfs when HIDAPI fails to discover the device. A missing HID node means the app must run on the host or in an environment with access to that node. A permission error calls for the narrow vendor-interface rule above.

Open **Host Profiles → Manage… → Add built-in profile** to add a fresh copy of a preset to an existing library. The new presets use full-frame patterns and work without per-key calibration.
