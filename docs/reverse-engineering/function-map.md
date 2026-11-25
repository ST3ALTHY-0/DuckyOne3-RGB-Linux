# V1.16 function map

Code addresses are even Thumb instruction addresses. Function pointers have bit zero set. Names below describe observed behavior. Entries marked local were established by the vector table, runtime pointer literals, or isolated headless disassembly where the connected Ghidra import lacks function objects.

| Address | Function or instruction | Evidence and confidence |
|---|---|---|
| `0xA530`, `0xA4C4`, `0xA47C` | Reset trampoline, C startup, scatter walker | Vector at `0x04`, `BLX` at `0xA492`, main call at `0xA4D6`. High |
| `0x42D2`, `0xA440` | Scatter decompression, zero initialization | Function displacements in `0xA4B4` and `0xA4A4`. High |
| `0x8E52`, `0x95CA` | Main and startup-only special loop | Calls lighting at `0x8E92`, `0x95EE`. High |
| `0x00C0`, `0x02364` | Lighting/effect initialization and initial settings | Descriptor table stores at `0x00C6` onward. High |
| `0x3160`, `0x4BE2` | Logical RGB16 setter and remapper | `0x3170 BL`, `0x318E/90/92 STRH`, two scans at `0x4BEE/0x4C0E`. High |
| `0x2312`, `0x305A`, `0x319C` | Clear both effect work grids, clear one internal work pixel, clear main grid and highlight one pixel | Thumb stores at `0x232C–0x233E`, `0x305A` body, `0x31B2–0x31F8`. High |
| `0x321C` | Lighting service with effect callbacks and lifecycle transitions | Render flag `LDRB/STRB` at `0x326C/0x3276`, callbacks `0x33FE/0x342C`. High |
| `0x2748`, `0x29B4`, `0x2A0C`, `0x2A88` | Special-state overrides, preview state, timed notification fill, validation-failure sequence | Branches `0x327E/0x337C/0x33CA/0x328C`. High roles, medium UI purpose |
| `0x241C`, `0x2C9C` | Derive effect steps from palette settings, handle lighting key events | Calls `0x4008`, event remap at `0x2CE2`. High |
| `0x3B08`, `0x41A8` | Compose back page, byte copy | Calls `0x3B48/0x3B62`, publish store `0x3F8C`. High |
| `0x37A0`, `0x3914`, `0x39CC`, `0x3AC2`, `0x3F92` | Initialize output, suspend/restore driver, clear pages, force blank around flash jobs | Register accesses, 900-byte clear, render lifecycle calls. High code, medium event names |
| `0x3A18`, `0x3660` | Start bank and consume pending page, SPI0 ISR | Local, timer call at `0x52C4`, SPI vector at `0x78`. High |
| `0x52B0`, `0x52CA`, `0x52E4` | TIMER1/2/3 handlers | Local, vectors `0x64/0x68/0x6C`. High |
| `0x4C40`, `0x4BDA`, `0x57D6` | Scan/debounce service, scan tick producer, foreground timer callbacks | `0x52DE` sets scan byte, `0x8E8E` consumes via scanner, `0x8E86` runs callback list. High |
| `0x9E00`, `0x9F26` | USB IRQ and vendor OUT copy/rearm | Local, vector `0x9C`, call at `0x9ED8`, mailbox ready at `0x9F3C`. High |
| `0x963C`, `0x9654`, `0x9F0E` | Vendor foreground service, stock handler, vendor IN reply submission | `0x9646` original BL bytes `00 f0 05 f8`, reply call at `0x964A`. High |

## Writer inventory by ownership

The writer census combines decoded callbacks, direct xrefs, a whole-image literal scan, and inspection of stores and copies in the relevant functions. It covers observed foreground producers. Whole-program alias closure for every indirect callback remains open.

- **Native work RGB16.** Effect callbacks in [native effects](native-effects.md) and their common clear at `0x2312`. Literal sites include `0x031A`, `0x047A`, `0x0520`, `0x0726`, `0x08AE`, `0x0BB4`, `0x0CE6`, `0x0ED6`, `0x10CC`, `0x1340`, `0x1440`, `0x18FA`, `0x1BF0`, `0x1F36`, `0x20F4`, `0x21E8`, and `0x22C2`. This is a set of literal witnesses rather than a list of function boundaries.
- **Special/foreground RGB16.** `0x2748`, `0x29B4`, `0x2A0C`, `0x2A88`, and `0x321C` have direct stores. `0x305A`, `0x313C` (saves and restores one pixel around a clear), `0x3160`, and `0x319C` are explicit pixel/clear routines.
- **Calls into the setter.** Ghidra reports 55 direct BL sites. Six in `0x6908` (`0x694C–0x69CA`), three in `0x7EDC` (`0x8030/46/5E`), ten in `0x851C` (`0x85D6–0x8786`), and 36 in `0x5B0C` (`0x5B46–0x5BB2`, `0x5CCE–0x5E86`). The last routine is confirmed by local headless analysis. `0x5942` installs its Thumb pointer from literal `0x5AD8` in a foreground callback record. Ghidra MCP reports these 36 sites without a containing function.
- **Scratch and alternate source.** `0x2312` clears `0x20001BD0`, `0x068C/0x0888` use it for rates. `0x2364` generates the alternate-source hue gradient during startup. `0x2C9C` quantizes that source during editing. Every direct reference to `0x20001D94` resolved to initialization stores, the three key-event reads, or the compositor argument. Indirect aliases remain an allocation risk.
- **Driver pages.** `0x3B08` is the normal producer with five foreground call sites `0x3556/0x357A/0x35E4/0x35FC/0x361A`. `0x3AC2 → 0x53BC` clears both pages from init and lifecycle transitions. The output ISR only reads page data. V4 must have one foreground publisher per mode.
