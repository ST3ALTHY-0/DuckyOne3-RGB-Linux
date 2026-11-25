# V4 external RGB architecture

V4 keeps a separate committed RGB8 source and the stock double-buffered scanout path. The preimplementation pass refined the selector into a foreground supervisor at `0x8E92` and a compositor input shim at `0x3B0C`. Both native and external paths continue to call `0x321C` so that suspend/resume, timed callbacks, mode transitions and settings work retain their original timing. The compositor accepts the external source after its stock prologue and before any page writes. [Exact implementation specification](v4-implementation-spec.md)

## Hook options

| Candidate | Evidence and tradeoff |
|---|---|
| `0x8E92` alone | No-argument foreground call with an aligned eight-byte main frame. As a supervisor it is safe to wrap. As a full override it would suppress stock callbacks and output lifecycle |
| `0x8E92` and `0x3B0C` | Selected. Common prologue after source/overlay arguments are saved, covers all five normal calls, maintains native state and permits independent masks |
| `0x353A` | Shared pre-compose join with existing service frame. Fewer modified stack semantics but stock arguments are constructed afterward. Selective preservation would require duplicating caller decisions |
| Five compositor BL sites | Straightforward AAPCS interception and convenient for prototype disassembly. More independent patch checks and the same behavior required at five call sites |
| `0x33FE` and `0x342C` | Init/tick callbacks only. Special-state producers, configuration paths, and ordinary composition still run |
| `0x3A18` or `0x3660` | Too late to protect stock scanout ownership without driver changes. Adds IRQ load and timing risk |
| `0x95EE` | Startup-only special loop. Keep its normal path |

The retained native engine can keep publishing at its normal cadence even for a static external frame. Cache expanded/scaled colors by revision. External compositor passes skip if a previous back page is pending. Any later optimization that skips repeated output must account for the stock ready event, which the timer emits when it consumes pending at rollover.

## Ownership alternatives

| Approach | Reliability, compatibility and cost |
|---|---|
| Gate native effect generation and reuse the native frame | Minimal SRAM, but the effect frame remains shared with event, notification and profile writers. A narrow callback gate cannot enforce ownership |
| Separate external source with existing compositor | Selected. Isolates colors and retains mapping, native controls and timing. Requires explicitly initialized extension SRAM |
| Late scanout interception | Can remove expanded scratch, but must replicate four remaps, masking, swap and lifecycle invariants. Revisit after the baseline validates |
| Replace high-level engine | Allows more CPU optimization, but increases mode, indicator and compatibility work. Preserve the existing path for selective user access |
| Replace low-level engine | No demonstrated need. Adds electrical timing, scan scheduling and recovery risks |

RGB8 staging and committed storage use 456 aligned bytes and derived RGB16 scratch uses 452. RGB16 transport costs extra reports and increases state memory. Implement brightness as scalar scaling of the external source. Apply optional stock overlays after that scaling. Native brightness keys remain stock and do not affect external brightness. Host effects use frame updates. A future reactive feature can tap debounced events without altering typing or enabling key telemetry by default. [Framebuffer evidence](framebuffers.md)

The working allocation is 1,280 explicitly cleared SRAM bytes. Firmware emission and later hardware validation still require alias, stack and recovery-envelope checks. [Memory map](memory-map.md) · [Verification gates](v4-implementation-spec.md#failure-handling-and-verification)
