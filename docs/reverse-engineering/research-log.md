# Research log

## 2026-11-25 — stock V1.16 static investigation

1. Confirmed the connected Ghidra program name, length, Cortex/Thumb code and SHA-256. Cross-checked the original USB hook and existing V3 build and sender sources.
2. Used MCP decompilation, callers, callee lists, disassembly and raw memory on the setter, remapper, foreground lighting service, compositor, main loop, USB wrapper and adjacent routines. The live program maps the raw file only. Its SRAM references resolve through literal pools.
3. Disassembled the local exact-hash image with GNU Arm objdump. Inspected early Thumb callback code, slot shifts, IRQ vectors and missing Ghidra function entries. Recovered 12 native mode records from stores in `0x00C0`. Created functions in a disposable headless import to recover flow and pseudocode for vector/indirect targets absent from the live import, including `0x3660`, `0x3A18`, `0x5B0C`, `0x9E00`, and the effect callbacks. The first headless attempt conflicted with auto-analysis context. The isolated run with `-noanalysis` and explicit Thumb context succeeded.
4. Followed startup scatter dispatch, verified the compressed section bounds against `0x42D2`, and decoded 624 bytes to 1,044. Independently reproduced the four remap pairs and recovered endpoint descriptors. Confirmed secondary frame region is two scanout pages and that render-ready and pending are separate bytes.
5. Annotated the connected program via MCP with 12 function names, parameter names for setter/remapper/compositor, and comments at the publication, swap, effect dispatch and USB sites. Vector-only targets with no function object in the connected import are recorded by address in the [function map](function-map.md).
6. Mapped the nominal timer rates and output phase sequence. Compared five architectures and specified a separate external source with a retained stock scanout path and foreground frame transactions. No firmware was built, written or flashed. No USB commands were sent. A standalone model verified all 75 coordinate round trips through both mapping stages, all 120 chunk arrival orders, and swaps at bank zero from all five starting phases. This checks the proposed invariants using the recovered table and modeled state, without executing firmware.

## Resume without repeating the trace

- Open [lighting-engine.md](lighting-engine.md) for the core call chain. Start at `0x8E92` for a wrapper, `0x3F8C` for the publication store, and `0x3A40–0x3A54` for consumption. Read all five existing compositor call sites before patching an ABI. Use [native-effects.md](native-effects.md) for indirect callback entry points.
- The local image is `recovery_backup/vendor_v1.16.bin`. Reproduce the Thumb listing with `arm-none-eabi-objdump -D -b binary -marm -Mforce-thumb recovery_backup/vendor_v1.16.bin`. Treat linear decoding across data pools and startup bytes as candidates. Restart disassembly at a known Thumb entry to avoid accidental 32-bit predecode over an entry point.
- For startup SRAM evidence, run the existing [extractor](../../tools/extract_led_mapping.py) in a temporary directory with an absolute `--firmware` path. It writes `startup_sram.bin` in the working directory. Offsets `0x1AB/0x1B2` locate vendor endpoints, and `0x2E0` locates LED swap pairs. The decompression is offline.
- For missing functions in a separate headless import, use Raw Binary, `ARM:LE:32:Cortex`, base 0 and `-noanalysis`. Set TMode to 1 at each explicit even entry, disassemble, create a function, then decompile. Continue each trace through the literal pool and Thumb listing rather than relying on inferred return types.

## Open and prioritized

| Question | Evidence already collected | Next evidence |
|---|---|---|
| Can V4 reserve durable SRAM and flash? | Scatter zero-init ends at `0x20002820`; MSP and decoded RW extent known; stock FMC jobs address upper data flash | Whole-program bounds/alias audit, reserved stack depth, native data flash bank offsets, updater envelope and explicit linker allocation |
| Which native states must share ownership with V4? | Lifecycle `0x3232–0x3268`, page reset, validation gate and foreground callbacks identified | Correlate USBD state, flash busy and power/indicator cues to wrapper behavior; verify re-entry with a synthetic harness |
| Are all alternate/scratch writers identified? | Literal scan, effect table and explicit work/scanout writers cataloged | Trace aliases through profile import, preview and indirect event/flash callbacks in a headless stock project |
| Exact physical timing and LED layout | Timer target, SPI/PWM setup, bit sequence and GPIO row select established | Passive capture and optical output correlation when separately authorized. Verify RGB lane shifts, red latch-edge bit interpretation, and unused physical slots |
| Actual USB and input capacity | 1 ms descriptors and single-mailbox race risk established | Capture/report acceptance and scan latency with bounded traffic after authorized validation; check reply/rearm ordering |
| Official labels for native effects | All callback entries, periods and broad behaviors reconstructed | Compare stock mode order and lighting output for supported board profile |

Transport and optical performance claims must remain estimates until measured. The static evidence supports a V4 prototype design, with safe memory reservation and lifecycle validation required before treating it as production-ready.

## 2026-11-25 — V4 preimplementation verification

- Reconfirmed the repository stock hash and patch-site bytes with Ghidra MCP and independent Thumb disassembly. Verified that `0x8E92` is foreground with no consumed return and identified `0x3B0C` as a compositor shim after the 64-byte prologue. This supersedes the earlier plan to bypass the native scheduler.
- Cross-checked startup descriptors, decoded keyboard LED descriptor and USB packet geometry, alias candidates, MMIO/PDMA references, CPU copy/clear callers, and IRQ stack witnesses. Defined a 1,280-byte V4 allocation by explicitly extending startup zero-init. Static evidence supports the range for resolved paths. A full runtime collision proof and measured stack watermark remain open.
- Resolved the Caps Lock overwrite through the USB class control path and distinguished three other compositor features by trigger and physical bank/index. Verified the stock enumeration/configuration path, reset word behavior and 3-second modifier hold/config reset candidate. Retained stock bootloader passthrough.
- Finalized V4 wire framing, transfer semantics, independent V4 receive credit, optional final-chunk commit and an opt-in host inactivity lease. The [implementation specification](v4-implementation-spec.md) governs whenever older research notes describe a proposal.
- No V4 firmware was built, no USB commands were transmitted and no hardware or MCU configuration was changed.

The offline packet/layout model checked patch-site bytes against the stock image, all proposed SRAM subrange lengths and adjacency, 240 chunk-order cases across explicit and piggyback commits, lengths 0–65, bad CRC with retry and stock/V3 namespace separation. This model neither executed stock Thumb code nor established hardware alias or timing behavior.


## 2026-11-25 — implementation and offline verification

- Reviewed the working tree and rechecked the live Ghidra stock hash and hook bytes. Implemented V4 with the original scheduler and stock scanout, exact startup allocation, guarded RGB8 pages, and separate USB receive state. Added `0x964A` as an implementation refinement for stock IN accounting. Stock `0x9646`, LDROM/CONFIG handling and recovery profiles are untouched.
- Rebuilt V3 byte-for-byte to `78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258`. The final V4 offline candidate is 46,160 bytes with SHA-256 `bd30bea371897a00153d17aba8891ec78ba575865ec157f59d7b587a3d334d2a`. The build independently decodes generated hook destinations and disassembles each function from the actual output payload.
- Ran the production C harness and the emitted-Thumb veneer checks. Executed the generated ARM image with the Ghidra p-code emulator from the patched scatter clear through USB request/reply, RGB16 back page, original bank-boundary swap, displayed status and return to native. The transaction stayed within its write allowlist. Used simulated peripheral events and PRIMASK operations. This is not physical timing or a whole-program alias proof.
- Implemented the Linux controller and CLI on the shared device discovery and HID I/O. Native restoration, framing, invalid coordinates, stale replies and disconnect are covered offline. The host distinguishes V4 from unsupported transport without falling back to a legacy write protocol.
- Remaining hardware gates include untraced indirect writes and worst-case stack, actual USB scheduling and overlay output, stock-input latency, and the larger V4 programming/recovery envelope. No physical device was accessed.

## 2026-11-25 — Independent V4 hardware readiness audit

- Read all stock hook windows through Ghidra MCP. Imported the actual revised candidate into headless Ghidra and independently decoded 1,481 instructions, 330 direct edges, 78 literal words and eight switch entries. The live MCP project exposes the stock image and has no import/select operation.
- Fixed frame-selector guard checks at command/compositor use sites and prevented stale/busy USB replies from writing endpoint RAM before ownership checks. Revised V4 is 46,352 bytes, SHA-256 `77a3cc8693052fa5be882f0331c84487a219a21f199e170722d53f4aa73c565f`. V3 rebuilt to its existing hash. All 15 offline tests and the C sanitizer harness passed.
- Rechecked the exact stock embedding and update flow in the official V1.16 PE. V4 spans 23 APROM pages and needs 828 reports. LDROM acceptance, erase scope, residual tail after a shorter restore, and independent recovery from dead APROM remain unverified. The stock APROM reboot command itself touches flash and is unsuitable for a read-only inspection.
- The [hardware readiness report](v4-hardware-readiness.md) records the SRAM writer ranges, limits of stack and emulation evidence, and the disabled proposed profile. **NO-GO** for programming. No keyboard, USB transport or configuration register was accessed.
- The actual generated Thumb image passed 2,000 end-to-end emulated commits through stock page selection with a checked store allowlist. A separate expanded smoke run covered lease expiry, suspend/resume metadata, sequence exhaustion, corruption and native mode/profile publication. Maximum hardware stack depth and asynchronous bus interactions remain open.
