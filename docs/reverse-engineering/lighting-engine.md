# Lighting engine

## Foreground and interrupt scheduling

**High.** Reset vector `0x04` holds `0xA531`. The reset path reaches `0xA4C4`, runs scatter loading through `0xA47C`, then calls main at `0xA4D6 → 0x8E52`. Main calls LED setup and effect initialization via `0x8E6C → 0x00C0 → 0x37A0`. Startup can also enter the special loop at `0x95CA`, with a second lighting call at `0x95EE`.

| Foreground call | Target and role |
|---|---|
| `0x8E86` | `0x57D6`, elapsed-time callback list |
| `0x8E8A` | `0x4440`, flash job state machine. Calls `0x3F92` around flash work to blank scanout |
| `0x8E8E` | `0x4C40`, scan/debounce service. GPIO scan, 5×15 six-byte key state records and four-byte event records |
| `0x8E92` | `0x321C`, lighting foreground service |
| `0x8E96` | `0x963C`, vendor HID mailbox service |

**High.** SPI0 ISR `0x3660` shifts the active page. TIMER1 ISR `0x52B0` calls row starter `0x3A18`. At the bank 4→0 rollover, a pending frame triggers an active-page toggle and sets render-ready `0x200027B0` (`0x3A40–0x3A54`). The foreground tests and clears render-ready at `0x326A–0x3276`. The compositor sets the separate pending byte `0x200027B3` at `0x3F8C`. Initialization seeds render-ready at `0x38E6`.

**High.** At `0x3232–0x3268`, `0x321C` checks request byte `0x200027ED` and latched state `0x20002690`, executing `0x3914` or `0x39CC` on transitions. The former stops normal row service and changes GPIO/PWM state. The latter restores PWM/output, resets pages and restarts the row timer. Both branches call `0x2FD0`, which clears native work buffers through `0x2312`. Treat these as output lifecycle transitions, including when external mode is active. **High.** USB bus events write `0x200027ED` through the state-block literal `0xA0A4`. `0x9E52` clears on reset, `0x9E5E` sets on suspend, and `0x9E7A` clears on resume. End-to-end blanking and resume timing still require measurement.

## Native mode state and dispatch

| State | Evidence | Confidence |
|---|---|---|
| `0x20001495`, requested mode | `0x33D8–0x33DA`, literal `0x3628 = 0x20001494` then byte +1 | High |
| `0x20002680`, selected mode cache | `0x33DE–0x33EA`; starts at sentinel 12 in `0x00C0` | High |
| `0x20002681`, effect tick counter | `0x3416–0x3424` | High |
| `0x20001934`, 12×12-byte effect descriptor table | `0x00C0` initializes native RGB base + `0x1C4`; dispatch multiplies mode by 12 | High |
| `0x20002670`, foreground lighting state | Literal `0x34E4`; offsets +4/+5/+6/+8 manage timed override, +0x12 special state, +0x17 edit/preview, +0x1F notification state | High accesses, medium role names |
| `0x2000269E`, startup validation gate | `0x9406–0x9412` sets result after comparisons. Lighting uses alternate path `0x328C → 0x2A88` when zero | High |
| `0x200014EC`, profile/state discriminator | `0x3510`, `0x35C0`; changes overlay and indicator behavior | High accesses, medium semantics |

On a normal tick, changing requested mode triggers the init `BLX` at `0x33FE`. A nonzero period triggers the tick `BLX` at `0x342C` when the render-opportunity counter reaches that period. Native render then reaches one of five calls into `0x3B08`. Mode dispatch is only one branch of this service. Other branches fill or clear pixels directly, render special sequences, select alternate RGB16 source `0x20001D94`, and enable profile overlays.

## Why the V3 pixel disappears

**High.** V3 intercepts the stock `BL 0x9654` at `0x9646`, writes a single native work pixel through `0x3160`, and sets render-ready. The next lighting iteration runs native producers before composing. For example, mode 9 uses `0x10B0` for both init and tick, writing palette RGB across all 75 slots. Mode 0 calls `0x2312`, clearing the work buffers. Other effects change selected pixels, fade existing values, or overwrite the entire grid. A write can therefore be replaced before the first composition or after a transient presentation. V3 also asserts render-ready before checking pending. If a previous page is waiting to become active, the stock compositor could start another write into that page before the timer swaps it. This follows from ordering in the static code. It is a separate possible race, with no captured occurrence. Actual lifetime depends on effect phase and profile state.

**High.** Even if the work pixel survives, `0x3B08` can choose the alternate RGB16 source, override pixels with an enabled nonzero RGB444 profile entry, or apply special-key/indicator writes. Disabling only the native effect callback leaves key-driven and configuration writers plus these compositor branches. For persistent external RGB, establish independent source ownership and a defined overlay policy.

See [native effects](native-effects.md), [framebuffers](framebuffers.md), and the [V4 design](external-rgb-design.md).

## Hook verification

The proposed foreground call at `0x8E92` is a no-argument BL from the steady-state main loop. Main has only its eight-byte frame live at that point. `0x8E8E` handles scan/debounce, `0x8E96` handles vendor USB, and `0x8E9A–0x8EEC` is stock USB/pin status housekeeping and loop control. Ghidra found the sole main entry call at `0xA4D6`. The separate startup loop at `0x95EE` uses lighting before ordinary app operation.

The lighting scheduler covers more than native generators. It handles suspend transitions, timed state at `0x3292–0x3374`, an indirect completion callback through the pointer at state +8 (`0x32CA`), configuration/edit/blink paths and profile counters. Key scan and keyboard USB reports have independent entry points, but bypassing this scheduler can strand stock mode/configuration transitions. Use `0x8E92` for mode supervision and `0x3B0C` for input substitution, keeping stock work scheduled. Keep the stock nominal cadence when static external frames are held. If dirty-only output or suppressed native callbacks are pursued later, establish a separate ready clock or prove safe replacement for the existing completion-driven cadence. [ABI and patch sites](v4-implementation-spec.md#patch-sites-and-abi)

The compositor shim begins just after a 64-byte stock frame is established. It can service all five calls without patching the separate call sites. The join at `0x353A` is another plausible hook but occurs before stock constructs its final overlay arguments. The two callback gates at `0x33FE/0x342C` leave other writers and modes active. Rewriting the SPI or TIMER1 path adds ISR load and risks row timing. See the [architecture comparison](external-rgb-design.md).
