# Ducky One 3 SF RGB V1.16 reverse engineering

The stock engine has separate effect and scanout buffers. V3 writes a pixel into the native effect work area, then wakes the native compositor. Native effects can change that pixel before it reaches scanout, and native overlays can replace it during composition. V4 owns its source frame and uses the stock compositor and scanout handshake. The specification preserves the stock scheduler and substitutes the input after the compositor prologue.

This investigation covers the 42,942-byte stock APROM image loaded at address zero. Its SHA-256 is `966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844`. Verify against the [stock recovery reference](../../tools/recovery/hardware-recovery.md) before applying any address in these notes. Ghidra annotations and these documents are the deliverables. Firmware and hardware operations were outside this investigation.

| Document | Contents |
|---|---|
| [Lighting engine](lighting-engine.md) | Main loop, scheduling, mode state, V3 overwrite |
| [Function map](function-map.md) | Code entries, call sites, writer inventory |
| [Memory map](memory-map.md) | Startup sections, SRAM objects, stack, flash |
| [Framebuffers](framebuffers.md) | Source and composed formats, mapping, publication |
| [LED driver](led-driver.md) | SPI, GPIO, row timer, interrupts and rates |
| [Native effects](native-effects.md) | All 12 callback records and algorithm summaries |
| [External RGB design](external-rgb-design.md) | Architecture comparison and V4 implementation gates |
| [USB protocol design](usb-protocol-design.md) | Bulk reports, frame transactions, timing and host flow control |
| [V4 implementation specification](v4-implementation-spec.md) | Preimplementation findings, exact hooks, allocation, wire formats and gates |
| [V4 hardware readiness](v4-hardware-readiness.md) | Independent binary audit, recovery evidence and programming decision |
| [Research log](research-log.md) | Reproduction steps, assumptions, and open work |

**Confidence notation.** High means corroborated by instruction bytes, literals, vectors, descriptors or decoded startup data. Medium means a likely interpretation of verified accesses or control flow. Open means additional static or hardware evidence is required. A design proposal is labeled as such.
