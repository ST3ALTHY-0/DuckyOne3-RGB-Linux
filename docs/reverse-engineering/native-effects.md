# Native lighting effects

**High.** The table starts at `0x20001934`. Each record is a little-endian period halfword, two padding bytes, an init Thumb pointer, and a tick Thumb pointer. Reconstruct the runtime data from stores in `0x00C0` and the literals at `0x2A4–0x2F8`. The addresses below have their Thumb bit cleared. Periods count serviced render opportunities. Labels describe the observed algorithm. Marketing names and the hotkey order vary by configured profile.

| ID | Period | Init | Tick | Algorithm evidence |
|---|---:|---|---|---|
| 0 | 1 | `0x0268` | `0x0268` | Clear work buffers through `0x2312` |
| 1 | 11 | `0x0270` | `0x02FC` | Initialize palette-derived steps. Each tick shifts every row by one slot using a reverse index loop, and updates index zero with an R→G→B→R ramp. Direct work-frame addresses from `0x031A` onward |
| 2 | 7 | `0x0470` | `0x04F4` | Seed one channel from palette +0x16, then run frame-wide R→G→B→R ramps with a shared phase byte and saturation at `0xFFFF`. Bases at `0x047A` and `0x0520` |
| 3 | 7 | `0x0870` | `0x0888` | Clear and reset effect state, decay existing pixels, seed pseudorandom palette colors and per-pixel decay rates. PRNG `0x40DC`, work/scratch literals `0xA0C/0xA10` |
| 4 | 6 | `0x09F0` | `0x0A18` | Reset lists and counters, track columns and populate moving colored columns. List helpers `0x4204/0x42AC`, whole-column stores after `0x0BB4` |
| 5 | 7 | `0x0672` | `0x068C` | Clear and seed PRNG, use per-key event state for random palette colors with individual decay rates. Replicates special slots using `0x41A8` in tail |
| 6 | 13 | `0x0C08` | `0x0CA0` | Derive channel decay from RGB palette and speed selection. Event-marked pixels take selected color, then fade. Copies a common special-slot color |
| 7 | 13 | `0x0DCC` | `0x0E5C` | Event-driven center and neighborhood lighting. Center uses configured palette intensity, neighbors use values shifted right three. Neighbor banks differ by `0x5A` |
| 8 | 6 | `0x1116` | `0x11B4` | Full-grid breathing envelope. Init derives channel step sizes, tick ramps three shared values up and down and writes to all 75 positions |
| 9 | 15 | `0x10B0` | `0x10B0` | Solid configured RGB444 palette color. Unconditionally writes all 75 source pixels |
| 10 | 4 | `0x1374` | `0x1404` | Staged moving pattern with per-channel fade, phase steps grouped in 21-step intervals, position lists and repeated writes through `0x1Dxx` |
| 11 | 6 | `0x1E30` | `0x1EE0` | Per-row moving trails. Limits tracked slots per row, advances column indices, fades prior pixels, and uses per-position state to seed trails |

Init/tick pointers and periods are high confidence. Algorithm descriptions are high confidence for the arithmetic and writes, medium for visually named effects. In particular IDs 1, 2, 4, 10 and 11 should be compared against stock visual output before assigning official mode names.

`0x00C0` populates a 12-byte cycle order, either numeric order or with mode 9 second. `0x20002640` is shared native effect state. Its RGB16 step values are commonly at +0x20/+0x22/+0x24. `0x20001494` holds palette, selection and speed data. Native RGB brightness is a property of each generator and profile overlay. The serial driver consumes unsigned 16-bit intensity directly.

Key events are formed by `0x4C40` and routed through the callback stored at `0x200027E4`. Init at `0x5942 → 0x4A1C` installs Thumb pointer `0x8BDD` from literal `0x5AAC` at `0x200027E4`. The foreground event path around `0x8BE0` calls `0x2C9C`, which remaps coordinates and stores event state in `0x20002438`. It also samples the alternate RGB16 frame for configuration/edit operations and calls `0x241C` or `0x2312` in those paths. `0x7C88` has additional preview/clear operations. A device-side reactive V4 effect can consume a bounded copy of debounced events at this layer while leaving scanning and HID report construction intact.
