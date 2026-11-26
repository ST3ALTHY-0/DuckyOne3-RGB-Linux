# Architecture and formats

## Source tree

```text
controller/
├── pyproject.toml
├── src/ducky_rgb/
│   ├── app.py, window.py, widgets.py, keyboard.py, layer_editor.py
│   ├── protocol.py, transport.py, simulator.py, worker.py
│   ├── devices.py, effects.py, engine.py
│   ├── platforms.py, storage.py
│   └── assets/
├── tests/
├── packaging/
└── docs/
```

## Boundary map

- `protocol.py` owns the V4 wire client. The parent repository’s Linux CLI imports it through its existing `tools/rgb_v4.py` entry point. Neither transport needs Qt.
- `transport.py` defines the unnumbered 64-byte transport contract and the Cython `hidapi` backend. Its PyPI distribution is named `hidapi` and the import is `hid`. On write, HIDAPI takes a leading zero to represent the omitted report ID. On read, Studio accepts the native 64-byte form and normalizes a 65-byte zero-prefixed report where present. An empty read is a timeout. Normal typing collections and LDROM are ignored.
- `simulator.py` models the vendor namespace, staging, CRC, pending scanout, brightness, overlays, session lease and injectable transport faults. Scan periods and reply latency are configurable. Overlay flags are simulated as control state. The real firmware’s overlay pixel operations and power transitions are outside the model.
- `worker.py` owns transport and session resources on one thread. Qt receives status and counters through queued signals. The worker retains one replaceable desired output, drops obsolete unsent frames, suppresses duplicate frames, retries tagged transactions, distinguishes accepted from displayed and renews a bounded lease. A lost reply is reconciled by the wire client. Before exhausting sequence 65535, the next frame renews the session. Disconnect triggers same-path rediscovery and another CAPS exchange. Open/close remains serial, and multiple discovered keyboards can be selected one at a time.
- `devices.py` owns device identifiers, physical keys, geometry and verified slot assignments. `engine.py` composes complete normalized sRGB frames independently of HID. `effects.py` registers deterministic effects and parameter definitions. Each layer has speed, phase, opacity, brightness, key mask and blend operation. Optional gamma is applied after composition. Global preview brightness is local; the actual output setting uses the firmware's RGB16 brightness control. Recorded shared address memberships resolve to the first matching painted key by stable physical key ID ordering. A key with several addresses shows their average in preview.
- `window.py` coordinates editor state. `layer_editor.py` builds layer properties declaratively and `widgets.py` holds shared Qt controls and themes. `keyboard.py` is the high-DPI keyboard canvas and focused reactive input source. Rendering follows monotonic time regardless of I/O backlog. Static profiles render on edits and use only periodic lease renewal while active.
- `platforms.py` handles runtime capabilities and desktop startup. Qt supplies tray, notifications, dialogs and window-system integration. The keyboard engine consumes normalized key ID, down state, event age and capped aggregate count, with no cross-platform capture dependency. Future audio, screen, app and power services should provide opt-in timestamped data snapshots through adapters. Current hardware events use background HID polling.

### Add an effect or model

Give an effect a stable ID, declaration, category, validated parameter definitions, and deterministic implementation operating on normalized coordinates and elapsed time. Return one RGB float triplet per point. The property editor generates controls from the declaration. Add fixture-based effect tests and avoid accessing hardware or OS services from renderer code.

To add a keyboard model, define its geometry and frame layout in the device registry, provide a vetted HID identity and negotiated driver, and add a matching profile/map validator. Reuse the keyboard canvas and compositor. V4 protocol geometry is validated for this firmware only. A new transport must implement timed unnumbered payload reads, writes and reliable cleanup. New protocols require their own wire clients.

### Profile schema

`version: 2`, `device` (registry ID), `name`, `description`, normalized `brightness`, optional `gamma`, integer `fps`, `overlays`, `groups` and an ordered `layers` array. Each layer contains `effect`, `name`, `enabled`, `opacity`, `brightness`, `speed`, `phase`, `blend`, `mask`, `params` and per-key `paint`. Masks and paint use physical key IDs. Palette values use six-digit RGB hex strings, and optional stops are normalized positions. A version 1 import defaults gamma to 1 and groups to empty. Save uses an atomic replacement in the containing directory. Host profiles never change onboard profiles.

### LED mapping schema

`{"version":1,"device":"ducky-one3-sf-ansi","slots":{"0":{"keys":["Esc"],"verified":false}}}` illustrates the schema with a **provisional** assignment. Keys can share a slot or have multiple slots. An empty keys array with verified true marks an observed unused slot. Omitted slots are unknown. Use model- and board-appropriate trusted calibration data. Provisional entries do not change physical key addressing. Firmware slot index is `bank * slots_per_bank + index` for this driver.

## Implementation checklist

- [x] Independent package, shared protocol, HIDAPI filtering and simulator
- [x] Layout geometry, deterministic effects, compositing, rendering clock
- [x] Editor, profiles, painting, calibration, ACK diagnostics and transport worker
- [x] Optional focused input, tray, autostart, native leases and reconnect behavior
- [x] Three-platform CI and native packaging definitions
- [ ] Verify native CI packages and physical transports on Windows and macOS
- [ ] Complete physical LED maps and stress/suspend/overlay testing
- [ ] Add opt-in global input, audio/screen sources and native power adapters

### Optional platform integrations

Focused Qt input is the current reactive source. A global source would need device-scoped selection and explicit consent before subscribing. Linux screen synchronization should use the desktop ScreenCast portal and its PipeWire stream where supported. Accept cancellation and an absent portal backend as ordinary capability results. [XDG ScreenCast API](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)

On Windows, Raw Input can distinguish keyboard devices and WASAPI loopback can supply output audio. Any future listener should preserve ordinary keyboard message handling and discard raw input after computing lighting state. [Microsoft Raw Input](https://learn.microsoft.com/en-us/windows/win32/inputdev/using-raw-input) · [Microsoft WASAPI loopback](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording)

On macOS, evaluate ScreenCaptureKit for consent-based screen and audio streams on the appropriate OS version. Feed only downsampled colors or aggregate audio values into the renderer. These optional sources are outside the current application. [Apple ScreenCaptureKit](https://developer.apple.com/documentation/ScreenCaptureKit)

The ANSI display geometry follows the Standard Layer diagram in the One 3 SF manual. The diagram establishes key geometry and labels. Slot assignments come only from calibration or an imported map. [Ducky One 3 RGB manuals](https://ducky.global/products/one-3-rgb)
