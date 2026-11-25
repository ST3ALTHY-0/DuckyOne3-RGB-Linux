# V4 external RGB implementation specification

## Scope and release gates

This specification targets only the stock Ducky One 3 SF RGB V1.16 APROM, 42,942 bytes, SHA-256 `966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844`. It defines an offline implementation target. **Verified** refers to stock instructions, descriptors or documentation. **Design** refers to V4 behavior that has yet to be implemented. **Open** marks a release gate or a hardware-dependent result.

The first implementation preserves stock scheduling and changes the compositor input while external mode is active. Native effects may continue updating their private work frame. This retains timed callbacks, profiles, key handling, and output lifecycle. Reducing native effect CPU load is a later optimization. [Architecture decision](external-rgb-design.md)

## Patch sites and ABI

All code locations below are even Thumb instruction addresses. A stored code pointer has bit zero set. Verify every stock byte before emitting a patch. All new branch targets and literal pools must be within the allocated extension image. Recheck the emitted disassembly.

| Stock location | Original bytes and operation | V4 design |
|---|---|---|
| `0xA4A8` | `08 20 00 00`, scatter clear length `0x2008` | Extend to `0x2508`, bytes `08 25 00 00`, to reserve and zero 1,280 extension bytes on every APROM startup |
| `0x8E92` | `FA F7 C3 F9`, `BL 0x321C` | Foreground supervisor. Observe lifecycle and swap state, then call stock lighting exactly once |
| `0x3B0C` | `B9 48 80 7A`, literal load then `LDRB r0,[r0,#10]` | Common compositor input shim, after original prologue |
| `0x8E96` | `00 F0 D1 FB`, `BL 0x963C` | Foreground vendor service mux. Give stock mailbox precedence and process at most one V4 packet |
| `0x9ED8` | `00 F0 25 F8`, `BL 0x9F26` | OUT veneer. Capture actual length before the original receive/rearm operation |
| `0x009C` | `01 9E 00 00`, USBD vector Thumb pointer `0x9E01` | IRQ veneer. Capture reset, detach, suspend/resume, and vendor IN completion. Call the stock ISR with its original context contract |
| `0x52F8` | `00 F0 25 FA`, `BL 0x5746` | TIMER3 tick veneer. Increment a V4 32-bit millisecond counter and preserve the original tick |
| `0x5B2A` | `02 F0 01 FF`, `BL 0x8930` | Settings-reset chord veneer. Revoke V4 ownership, then perform the original call with r0 = 1 |
| `0x964A` | `00 F0 60 FC`, `BL 0x9F0E` | Implemented shared stock/V4 IN-arm accounting. Stock TX mailbox remains the source for stock replies |
| `0x9646` | `00 F0 05 F8`, `BL 0x9654` | Keep stock. This is the V3 patch site and the unchanged command passthrough in V4 |

**Verified foreground context.** Startup calls `0x8E52` at `0xA4D6`. Main saves `{r4,lr}` and never returns in normal operation. At `0x8E92`, `0x4C40` has returned, SP is the main frame base, and following code invokes the no-argument vendor service at `0x8E96`. There is no valid lighting argument in r0–r3 and no return consumed. Incoming BL sets LR to `0x8E97`. Preserve r4–r11, SP and return continuation as under AAPCS; retain r9 as supplied by stock. r0–r3, r12 and condition flags are caller-saved. Maintain 8-byte alignment across ordinary BL boundaries. Low registers can be saved with Thumb-1 PUSH. A veneer that uses high registers must save/restore them explicitly. `0x95EE` is the separate startup-only lighting caller and continues to run stock with zeroed V4 state.

**Verified compositor context.** `0x3B08` pushes `{r0,r1,r3,r4-r7,lr}` and subtracts 32 before `0x3B0C`, for 64 bytes total. At the shim entry, the original stack frame has source, r1 flags, r3 flags and caller LR at +32, +36, +40 and +60. The three caller stack argument words are at +64, +68, +72. They supply profile base, two-byte profile control records and profile count. All five stock callers allocate those words as outgoing scratch and exit after composition. On native pass-through replay the literal load from `0x3DF4` and the active-page `LDRB`, then resume at `0x3B10`. On external compose, adjust the saved source and permitted overlay arguments, then replay the same instructions. A pending page in external mode returns through `0x3F8E` without publishing. Restore SP to the stock 64-byte frame before either continuation. Preserve the live r1–r3 values on the native path, all callee-saved registers, and the saved original caller LR. The stock epilogue discards outgoing volatile-save slots. The scheduler and compositor run with interrupts enabled. Keep normal foreground scan service near its 1 ms tick and add no blocking loops. Every added IRQ path should be limited to constant-size metadata and at most one 64-byte transfer. Compare scan-service gaps and LED row deadlines (nominal 667 µs) against stock in the first hardware pass.

**IRQ contract.** The vector veneer preserves EXC_RETURN and uses the handler MSP, maintaining 8-byte alignment before calling stock ISR. Read the pre-ack interrupt snapshot. Keep stock acknowledgment, endpoint setup, keyboard endpoints and packet SRAM addresses. Ordinary BL veneers preserve callee-saved registers including live r4–r7 of both original IRQ callers. Use aligned atomic words or bytes between IRQ and foreground. Preserve the caller's interrupt state through any bounded critical region.

## SRAM reservation and cost

**Verified** application scatter clear is `[0x20000818,0x20002820)` and decoded initialized data is `[0x20000000,0x20000414)`. Nuvoton’s exact NUC1261SG4AE device-pack entry defines 20 KiB at `[0x20000000,0x20005000)`. [Device memory entry](https://raw.githubusercontent.com/OpenNuvoton/cmsis-packs/master/Nuvoton_DFP/Nuvoton.NuMicroM0_DFP.pdsc#L5485-L5493) USB packet SRAM is part of the USBD aperture, not this range. No stock data allocation or peripheral destination was resolved at the proposed extension address. Complete dynamic write exclusion and actual stack watermark remain open. **Design reservation** is `[0x20002820,0x20002D20)`, conditional on the bounds/watermark tests in [memory-map.md](memory-map.md). The enlarged startup descriptor establishes allocation and initialization. It does not prove that hidden stock writers cannot alias it.

| Half-open range | Bytes | Purpose |
|---|---:|---|
| `0x20002820–0x20002904` | 228 | RGB8 page A, 225 used |
| `0x20002904–0x200029E8` | 228 | RGB8 page B, 225 used |
| `0x200029E8–0x20002BAC` | 452 | Derived RGB16 work-coordinate scratch, 450 used |
| `0x20002BAC–0x20002BEC` | 64 | Private V4 receive slot |
| `0x20002BEC–0x20002C2C` | 64 | Zero-filled reply construction |
| `0x20002C2C–0x20002D1C` | 240 | Session and transport records, epochs, timing, sequence/coverage, render revisions, counters and overlay controls |
| `0x20002D1C–0x20002D20` | 4 | Tail guard, initialized by the supervisor after reset for diagnostic builds |

Keep frame arrays at four-byte alignment. Use bounded indices, compile-time offset/size assertions, no heap and no automatic frame arrays on MSP. Switching the two RGB8 page indices commits the frame without copying. RGB16 staging and committed doubles source storage from 456 to 904 bytes with alignment. Arbitrary brightness would still need derived RGB16 scratch or a verified compositor scaling path. RGB16 improves input precision but reduces bus efficiency and buys little for RGB8 desktop sources. The first ABI is RGB8 only. Estimated extension flash is 4–8 KiB at or after `0xA7C0`, including veneers, tables and protocol logic. Audit the exact final image size against the updater envelope and persistent storage. Physical APROM capacity alone does not authorize a larger write.

## Output and lifecycle state

All owner transitions, frame validation, brightness and rendering run in foreground. IRQ code maintains only transport metadata, timer and bus epoch. `NATIVE` is zero and requires no initialization before the first hook. A session is a volatile 32-bit nonzero client token, with one owner at a time. Clear the token and staged state on closure. The stock validation byte `0x2000269E` must be nonzero, USB configured and active, and no observed reset/settings-reset request pending before accepting takeover.

| State | Operation and transitions |
|---|---|
| 0 `NATIVE` | Stock output, no active session. Opening a valid token moves to `ARMED` and starts the first-frame deadline |
| 1 `ARMED` | Accept staging while stock output continues. A valid commit creates committed intent and changes state to `ENTER_PENDING`. First-frame inactivity of 2,000 ms terminates the session |
| 2 `ENTER_PENDING` | Wait for pending clear and settle a preceding native swap. At the next eligible stock compositor pass publish the committed frame and move to `EXTERNAL`. A close/loss before publication goes to `RETURN_PENDING` |
| 3 `EXTERNAL` | At eligible compositor passes publish the last committed frame, scaled with the current brightness, and apply only selected overlays. Newly accepted content changes the next publication. Close, lease expiry, bus event, reset activity or diagnostic integrity failure moves to `RETURN_PENDING` |
| 4 `RETURN_PENDING` | Reject content writes and invalidate the session. Resolve any prior pending page, then restore stock composition. If stock drivers are suspended, let their lifecycle code run and finish re-entry on resume. An already-published page can reach scanout during this handover. No new external generation may be accepted |

If an IRQ changes bus epoch during an expensive foreground operation, invalidate the response and discard the work at the next foreground check. An already-started in-flight composition may complete before the next lifecycle iteration. Treat its displayed record as invalid across epochs. Never hold IRQs disabled through expansion or composition. Test this exact race after implementation.

- **Power-on, software reset and bootloader return.** Stock reset and scatter initialization clear V4, including the new range. No persistent V4 state or config changes.
- **Enumeration and bus reset.** Stock initialization and SET_CONFIGURATION remain in `0x939A` and control handlers. A reset event at `0x9E4A → 0x9D6C` invalidates V4 even if the suspend flag stays zero. The standard SET_CONFIGURATION path at `0x9BC0–0x9BCA` stores wValue low into the control structure at `0x20000320`. The reset routine does not explicitly clear that word, so V4 must clear its own configured flag on reset and observe a new SET_CONFIGURATION. In the IRQ veneer, use the SETUP indication before stock acknowledgment and a validated eight-byte request at `0x40060100` as used at `0x98C4`. Accept configuration 1 and revoke on configuration 0. Require a new mode request upon reconfiguration.
- **Suspend/resume and disconnect.** USB IRQ metadata distinguishes bus reset, suspend/resume and floating USB detect. On suspend, detach or loss of configuration, discard V4 state and return to native. Preserve stock blanking and page clearing via `0x321C → 0x3914/0x39CC`. Resume starts native. Actual detach indication and control-transfer timing on this board remain release checks. A power loss inherently clears the owner.
- **Native keys, brightness and profile changes.** Continue stock mode and settings work. These changes update native state without changing external brightness or committed colors. If an overlay is selected, the effective stock overlay changes with its underlying state. On return avoid a gratuitous mode reset unless stock cache is inconsistent; the scheduler has kept the effects running.
- **Bootloader entry.** Non-V4 traffic is routed through the original vendor wrapper and handler. `0x9654 → 0x96C0 → 0x8B54` remains reachable in every mode. Keep the reset, recognized updater command and guard conditions stock.
- **Factory reset.** The candidate stock path starts a 3,000 ms hold timer from modifier state `0x88` and callback `0x5B0C` with argument type `0x0F`. It sets `0x2000250D`, enqueues settings work, and calls `0x8930(1)`. Preserve this path. The specific `0x5B2A` veneer revokes V4 before stock executes `0x8930(1)`, retaining the original argument and call/return semantics. Do not rely on polling the settings byte after the callback. Confirm the chord, other factory-reset paths if present, and stock feedback in the staged tests.
- **Host exit and incomplete transmission.** Graceful exit closes the session. Optional inactivity lease 0 or 1,000–60,000 ms. Default 0 holds the last image while the bus stays active. A nonzero lease permits crash fallback, refreshed only by valid session traffic. Staging expires independently after 1,000 ms without a valid chunk. Retain the previous committed image. While waiting for first content, expire the armed session after 2,000 ms even with lease disabled. TIMER3 veneer supplies the monotonic counter. Compare elapsed time using unsigned subtraction; bounds are below the half-wrap interval.

## Frame handoff and overlays

Expand/remap committed RGB8 in foreground on content or brightness revision change. Scale each `channel * 257` by `brightness / 65535` with deterministic round-to-nearest and full-scale identity. Reuse expanded scratch on subsequent turns. Pass `0x3B08` an immutable source in native work-coordinate order and let it compose the back page. Never start an external composition with `0x200027B3 != 0`. Track the expected alternate page and submitted frame/revision. Advance displayed only when pending clears and the expected active page is observed. This is **scanout selection**, not a sensor measurement of emitted light. Invalidate pending/displayed on lifecycle page clear, bus epoch change or forced native handover. The active page is read-only to all V4 code.

The default overlay mask is zero and removes all compositor overrides. This gives all 75 firmware slots independent RGB input. Physical legends, shared LED wiring and the stock red serialization caveat still apply. Mask bit 0 retains the stock Caps Lock white overwrite when the original bit is set. Bit 1 retains the stock Z/X/C channel marker group when the original r3 byte requests it. Bits 2 and 3 allow the two stock custom lighting zones (CM1 and CM2), using only records the selected stock call had enabled. The shim copies those control bytes to V4-owned scratch, clears disallowed enables, masks out r1 bit 1 when Caps is disabled and clears r3 when markers are disabled. Count zero when neither profile is enabled. Never reintroduce an override masked by the stock calling branch. Grouped profile replication remains part of the enabled profile operation. Advertise marker/profile capabilities only after their bench behavior is confirmed. [Overlay evidence](framebuffers.md)

## Exact vendor HID v1 format

The stock interrupt pair remains OUT `0x02` and IN `0x81`, 64 bytes each, 1 ms interval. Offsets below are relative to the device payload. Linux hidraw's leading zero report ID is host-side framing. Multi-byte fields are little-endian. Zero all pad and reserved bytes. Use the five-byte namespace `00 3A 52 34 E4`. The stock handler tests byte 4 = 1 before either of its subcommands, and V3 also requires byte 4 = 1. The new namespace is disjoint from both by construction. Full-length reports with other prefixes continue to stock, including vendor info and LDROM entry. V4 does not advertise the V3 per-key extension as an alternate transport.

### Request envelope

| Bytes | Meaning |
|---|---|
| 0–4 | Namespace `00 3A 52 34 E4` |
| 5 | Protocol major, `1`. `GET_CAPS` also accepts `0` for version discovery |
| 6 | Opcode below. Bit 7 must be clear |
| 7 | Opcode argument, zero where unused |
| 8–11 | Session token, zero for discovery and native status |
| 12–13 | Frame sequence, zero for commands without a frame |
| 14–61 | Opcode data, then zero padding |
| 62–63 | Nonzero request tag. Use a fresh tag for each distinct request and the same tag for its retry |

| Opcode | Request fields and effect |
|---|---|
| `01 GET_CAPS` | Argument, session, sequence and data zero. Return supported features and geometry |
| `02 SET_MODE` | Argument 1 opens external ownership with a fresh nonzero client token. Bytes 14–15 hold lease ms and byte 16 the requested mask. Argument 0 closes only the matching existing token, with data zero. Sequence zero. An identical retry of open returns current state without resetting it. Reusing a token with different open options is a conflict. A different owner is busy. A duplicate close of the most recently closed token is successful until another session opens |
| `03 CHUNK` | Argument = index 0–4. The fixed index identifies logical pixels `16*i` onward. Chunks 0–3 carry 48 bytes of RGB8 for 16 slots. Chunk 4 carries 33 bytes for the last 11 slots. Payload starts at 14. Require a session and a frame sequence in 1–65535 |
| `04 COMMIT` | Argument zero. Bytes 14–17 are CRC-32/ISO-HDLC of exactly 225 staged bytes in bank-major logical RGB order. Reflected polynomial `0xEDB88320`, initial and final XOR `0xFFFFFFFF`, test vector `123456789 → CBF43926`. Require full coverage and matching session/sequence |
| `05 GET_STATUS` | Argument, sequence and data zero. Zero token returns public mode and capability state with session frame fields zero. Matching token returns detailed state and refreshes an active lease |
| `06 ABORT` | Argument/data zero. Matching nonzero sequence discards only that staged transaction. A retry when that stage is already absent is successful unless the sequence was committed. The committed/displayed image remains valid |
| `07 SET_BRIGHTNESS` | Argument and sequence zero. Bytes 14–15 hold unsigned scale 0–65535. Changes current brightness revision. Repeat of the same setting is idempotent |
| `08 SET_OVERLAYS` | Argument holds mask bits 0–3, sequence and data zero. Reject any bit absent from the advertised supported mask. Changes overlay policy revision |
| `09 KEEPALIVE` | Argument, sequence and data zero. Matching token refreshes an enabled lease without changing the committed frame |
| `0A CHUNK_COMMIT` | Optional optimization, capability-gated. Same as index-4 CHUNK with argument 4, followed by CRC at bytes 47–50. Save commit intent even if the final chunk arrives out of order. Recheck the intent upon every valid chunk for that stage. If complete, report the commit result in that chunk reply. Incomplete intent reports INCOMPLETE. A busy commit keeps the intent and coverage for retry. A failed CRC clears the intent and leaves staged bytes for explicit retry or abort. An ordinary explicit COMMIT may complete or retry the same transaction using the same CRC |

Sequence increases strictly within a session. The first new sequence is 1. The next is the last accepted sequence +1. An aborted or expired incomplete sequence can be restaged. To avoid ambiguity with delayed retries, close and open with a new token before sequence wrap. A one-byte coverage mask tracks the five chunks. Duplicate chunks compare their exact canonical payload against the staged or most recently committed snapshot; equal duplicates succeed and differing bytes return conflict. Frames older than the last accepted sequence return stale. An incomplete explicit COMMIT reports the coverage mask and leaves staging intact without arming automatic commit intent. Wrong CRC leaves both the staging and published frame intact. To replace conflicting staged data, explicitly abort first.

Allow one staged sequence plus one committed-but-not-selected sequence. When COMMIT arrives while an earlier accepted generation still awaits scanout, return busy and keep the staged frame for retry. For a successful COMMIT, exchange staging/committed indices in one foreground transition, record CRC and increment a render revision. Reply acceptance can precede scanout. A duplicate COMMIT of the current accepted sequence and CRC reports the existing state without publishing a second generation. A differing CRC for that accepted sequence is CONFLICT. If a final-chunk commit intent already exists for an incomplete stage, an explicit COMMIT or repeated final-chunk intent with a different CRC returns CONFLICT until ABORT. Brightness or overlay changes do not increment content sequence. A separate revision reflects their requested rendering state. Next publication observes those settings deterministically. Clear staged state on reset/closure and reject old-token reports.

### Reply envelope

All V4 replies are 64 bytes. Bytes 0–5 carry the namespace and implemented major (1), byte 6 contains request opcode OR `0x80`, byte 7 holds status. Echo request token and sequence at 8–13 and request tag at 62–63 even on ordinary validation errors. For a short report, echo a field only if it was fully received. Do not expose stale bytes. Reply data is fixed for all opcodes.

| Bytes | Reply field |
|---|---|
| 14 | State code 0–4 from lifecycle table |
| 15 | Stage coverage bits 0–4 |
| 16–17 | Staged sequence |
| 18–19 | Last accepted sequence |
| 20–21 | Currently queued sequence, zero if absent |
| 22–23 | Last displayed sequence, zero if none |
| 24–27 | Current requested render revision |
| 28–31 | Last displayed render revision |
| 32–33 | Current brightness |
| 34 | Active overlay mask |
| 35 | Supported overlay mask |
| 36–39 | Capability bits. 0 RGB8, 1 explicit atomic commit, 2 CHUNK_COMMIT, 3 optional lease, 4 displayed status |
| 40–43 | Layout ID `0x01160001` for V1.16 5×15 logical slots |
| 44–48 | Slots 75, banks 5, slots per bank 15, pixels per full chunk 16, chunks per frame 5 |
| 49 | Vendor report size 64 |
| 50–51 | Active lease ms |
| 52 | Current transport flags. Bit 0 configured, bit 1 suspended, bit 2 prior external page pending. Remaining bits zero |
| 53 | Echo of request argument |
| 54–61 | Zero |
| 62–63 | Echo of request tag |

Status codes are `00 OK`, `01 BAD_LENGTH`, `02 BAD_VERSION`, `03 BAD_OPCODE`, `04 BAD_ARGUMENT`, `05 WRONG_SESSION`, `06 NOT_READY`, `07 BUSY`, `08 INCOMPLETE`, `09 CONFLICT`, `0A BAD_CRC`, `0B STALE_SEQUENCE`, `0C UNSUPPORTED`, `0D INTERNAL_FAULT`. Validation order is length, version, opcode, canonical fields/padding, readiness, token, sequence/coverage/CRC. Unrelated namespaces are never interpreted as V4. Unaccepted requests do not refresh leases or mutate the committed frame. Validate shapes before multiplying offsets or indexing. A bad length with the complete namespace can produce a V4 error. A shorter report cannot identify V4 safely and is dropped with no reply.

### Endpoint handoff and lower-overhead path

**Verified stock.** The OUT IRQ uses `0x9ED8 → 0x9F26`, reads from USB packet SRAM, copies 64 bytes regardless of actual length, publishes a shared ready byte, then rearms. The original foreground clear can overwrite a newer ready notification. The NUC1261 USBD endpoint MXPLD read reports actual received length before rearm. The firmware literals assign vendor OUT registers at `0x40060530` with MXPLD +4, vendor IN registers at `0x40060520`, and USB packet SRAM at `0x40060100`. USB IN completion is IRQ status bit 18, acknowledged at `0x9ECE`. [NUC1261 USBD register definition](https://raw.githubusercontent.com/OpenNuvoton/NUC1261BSP/master/Library/Device/Nuvoton/NUC1261/Include/NUC1261.h#L14560)

**Design.** OUT veneer reads actual length, rejects malformed short stock reports, and permits exact-length stock reports through the original path. Capture recognized V4 reports in the private slot, recording actual length and bus epoch before setting ready. Zero-fill short captures, never read beyond received bytes, and rearm immediately even when dropping a busy V4 receive. The IRQ never parses frame contents or waits. The foreground holds the slot until it has validated and stopped reading it, then clears ready exactly once. A report arriving while the slot is occupied is dropped and the host retries. No OUT request holds the endpoint armed state hostage. Power-off or disconnect can therefore never disable stock recovery merely because a V4 reply was unread.

Observe IN completion through the IRQ wrapper. Foreground tracks both stock and V4 IN submissions and serializes reply submission with existing vendor service. Preserve stock submission when a stock ready flag is present. If previous IN is busy, keep a V4 request queued until stock completion, bus invalidation or a 1,000 ms private-mailbox hold limit. Release the slot at that limit and let the host retry. In ordinary V4 traffic it may submit when prior V4 IN is drained, using the original USB packet destination and 64-byte MXPLD arm. Validate the segment, bus epoch and IN ownership before copying or arming. The audited build masks interrupts for the validation, bounded 64-byte copy and arm, then restores PRIMASK. Stock command traffic takes precedence. Concurrent vendor clients can supersede a reply on the shared endpoint; the client matches opcode, argument, token, frame and request tag, drains stale replies and retries idempotently. Advertise and test one outstanding request across both directions. Never interpret successful USB OUT submission as application acceptance. Exercise IN busy, bus reset during copy and missing-IN cases before enabling bulk transfers.

Five data reports plus explicit commit gives six request/reply exchanges per frame. With the final-chunk commit option, the same atomic validation fits in five. Four reports cannot hold 225 bytes at 48 payload bytes/report. A four-report design needs 225 color bytes across the four reports. An equal payload limit would have to be at least 57 bytes, leaving at most seven header bytes per report and still requiring space for commit metadata. That changes framing. Do not compress arbitrary pixels or pipeline in the baseline. The 1 ms interval is a USB scheduling bound. At one complete exchange per ms the theoretical six/five-report limits are about 167/200 frames/s, and at two ms they are about 83/100. Firmware acceptance and optical rates require measurement.

## Failure handling and verification

**Offline acceptance**

1. Verify the full stock hash and exact byte sequence of every chosen patch site. Verify entry alignment, return paths including the compositor skip, literal values, call operands, reserved SRAM bounds, and preservation of unpatched bytes. No output image or on-device code is part of this verification turn.
2. Before a firmware build proceeds to hardware, show bounded alias evidence for the new region using stock traces or an emulator configured from the vector, scatter output, peripherals, and stock valid profile inputs. Instrument reads/writes of both stock pages and the new block, including reset, profile loads, multiple native effect callbacks, USB control, flash callbacks, and suspend states. Run startup with nonzero fill and verify exact zero limits. Check V4 tail guard and memory weights. Validate stack with disassembly, emulator low-water logging and later hardware watermark. Bound new nested call chains and IRQ masking duration.
3. Test all packet lengths 0–64 and malformed namespaces, version, padding and bounds. Reproduce stock-branch and V3 collisions as non-V4 inputs. Cover all 120 chunk orders, missing chunks, duplicate replacement, out-of-order final intent, wrong CRC, last sequence and reopen, session mismatch, retries when arbitrary IN replies are lost, busy commit and wrap-safe expiry.
4. Model all five row phases, busy SPI, overlapping IRQs, brightness changes mid-frame, selected overlays, native→external→native, input events, stale staged and displayed states, flush on USB reset/disconnect, and suspend during composition. Assert that V4 never writes an active or pending page, any complete page is immutable until consumed, and the stock lifecycle remains the only driver reinitializer.
5. ABI checks include native register equivalence at `0x3B10`, valid stack arguments at all five callers, nested exception return, and no preserved-register drift in either foreground call hook. Verify both display and typing progress under bounded foreground work.

**Staged hardware validation, separate authorization required.** Establish a verified stock restore and separate input device before any write. Stage (1) offline artifact comparison and recovery dry run, (2) an explicitly approved default-native build and stock parity checks, (3) slow external per-key/solid and rollback checks, (4) complete-frame atomicity and each overlay, (5) suspend/reset/disconnect/reconnect/bootloader/factory lifecycle, (6) sustained traffic with passive USB and LED timing measurements, then input delay and scan missed-tick checks. Avoid deliberate loss of APROM or power during programming until independent recovery is established. Treat output throughput, safe flash envelope, detach handling, stock IN interleavings, exact physical indicator semantics and SRAM/stack runtime exclusivity as remaining gates.

**Stock recovery.** Retain the 42,942-byte hash-verified vendor binary and repository recovery tool. For a separately authorized restore, use only the existing inspected LDROM and exact identity checks (`0x33` version, PDID `0x01205212`, CONFIG0 `0xF7FFFF7C`, CONFIG1 `0x00033200`). Perform the documented offline packet dry run, enter or detect LDROM via the documented stock path, then use the existing `RESTORE-DUCKY-1.16` confirmation. Stop on profile mismatch or programming error and preserve the LDROM state for diagnosis. Verify APROM enumeration, typing, stock lighting and LDROM access after a successful restore. Independent hardware recovery and byte-for-byte readback remain unproven. [USB restoration procedure](../../tools/recovery/README.md) · [Hardware recovery limits](../../tools/recovery/hardware-recovery.md)

## Implementation notes

The implementation is in [v4.c](../../firmware/v4.c), [Thumb veneers](../../firmware/v4.S), and the [V4 builder](../../firmware/build_v4.py). The two storage indices select staging and committed RGB8. A software CRC validates all 225 bytes before publication. A native build of the production C functions exercises the wire state machine and simulated USB MMIO. The Thumb harness executes emitted branch and veneer instructions and checks preserved registers, stack alignment and both compositor continuations.

One additional hook at `0x964A` replaces stock `BL 0x9F0E`, bytes `00 F0 60 FC`, with the shared IN-arm helper. This retains the stock TX mailbox and reply format while tracking stock as well as V4 IN ownership. The stock command BL at `0x9646` stays in place. Correct MMIO and IRQ race behavior on real hardware still requires validation. Rejecting short unknown vendor reports prevents taking a stock action based on old bytes in packet SRAM. Only full-length stock reports are forwarded.

The candidate advertises the four implemented overlay mask bits for offline testing. Exact physical LED behavior is pending bench validation. No display claim is made beyond observed active-page selection. Zero lease holds the last display while configured, and short transfers or unrecognized firmware do not silently fall back to legacy V3 transmission.

### Hardware validation gates

Every stage below requires separate authorization. The candidate manifest is not a programming profile. Keep an alternate input device available, and keep a verified copy of stock V1.16 and its recovery procedure.

| Stage | Pass criteria |
|---|---|
| 1. Read-only inspection | Existing sysfs detection finds exactly one expected vendor collection. Verify stock image hash and recovery profile offline. Document board identity and independently available recovery before writing |
| 2. RAM and default-native behavior | On board or adequate SoC emulation, monitor stock writes in the proposed reservation through boot, all available modes, profile loads, key traffic and USB events. Measure stack low-water mark under combined load. Verify guards, neighboring memory and stock key/lighting behavior after candidate startup |
| 3. Session and static LEDs | Power-on starts native. Discover exact V4 layout. Open external mode without changing LEDs until first commit. Check black, full scale and representative one-key colors at boundaries and remapped slots. Return to native without replugging |
| 4. Frame commits and overlays | Truncate, reorder and retry reports. Incomplete or bad-CRC frames leave the last committed frame visible. Valid frame swaps at a bank boundary. Confirm each opted-in overlay separately and confirm opt-out preserves control |
| 5. Animation and input | Start slow and increase the rate while recording accepted and displayed throughput, missed scans, and keyboard latency versus stock. No lost or duplicated keys or modifier states. Investigate measurable regression before advancing |
| 6. Lifecycle and recovery | Verify host close, abandoned staging, lease expiry, reset, suspend/resume, disconnect/reconnect, native controls and factory reset. Under approved recovery conditions, confirm entry to the original LDROM path and stock restoration using only the existing profile |

Stop immediately on identity or hash mismatch, unexpected writable extent, diagnostics fault, unknown SRAM writer, stack collision risk, incorrect stock enumeration, stuck or missing keys, repeated reset, partial or torn output, failed suspend/resume, or loss of the known recovery path. After any programming or acknowledgment failure, preserve the observable state and follow the existing recovery guide.

### Reproducible test results

| Image | Bytes | SHA-256 |
|---|---:|---|
| Stock V1.16 | 42,942 | `966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844` |
| V3 | 43,084 | `78bd898284478e9b60ca7d3c4bfc8c4175e7f690961b68d42481143734609258` |
| V4 offline candidate, Clang 22.1.8 | 46,352 | `77a3cc8693052fa5be882f0331c84487a219a21f199e170722d53f4aa73c565f` |

The V4 payload is 3,408 bytes and the manifest reports 1,280 bytes of reserved SRAM. Compiler stack reports give 56 bytes for the vendor foreground function and 32 for its commit callee, or 88 for that added direct path. The compositor shim adds a 16-byte veneer plus a 32-byte C frame before returning to the stock body. These figures exclude the surrounding stock stack and exception frames.

The native C harness runs all 120 chunk permutations through each commit format, invalid lengths and indices, CRC and sequence failures, mode transitions, guard failure, and all 16,777,216 RGB8/brightness pairs. All 15 Python test cases passed. They cover the controller, build determinism, emitted veneer register behavior and unmodified recovery checks. GNU Arm objdump verified all nine patch locations and 330 direct branches in the extension. The Ghidra ARM execution model verifies the actual extension and stock scatter clear through a simulated USB-to-scanout transaction, including stock page rollover and native return. The lowest stack write observed in that transaction was `0x20000740` from a simulated foreground SP of `0x200007E0`. This is a witness for the exercised path. IRQ nesting, full native profile activity and physical USB timing remain outside that measurement.

Run the Ghidra test with an empty temporary project directory and the generated V4 image. This harness uses the 12.1.4 headless emulator API and models register values and bus events. It requires no attached keyboard.

```sh
mkdir -p /tmp/ducky-v4-ghidra
"$GHIDRA_HOME/support/analyzeHeadless" /tmp/ducky-v4-ghidra v4-test \
  -import /tmp/ducky-v4.bin -loader BinaryLoader -processor ARM:LE:32:Cortex \
  -noanalysis -scriptPath tests -postScript EmulateDuckyV4.java -deleteProject
```

Look for `V4 THUMB EMULATION PASSED` in the script output.

The [independent hardware readiness audit](v4-hardware-readiness.md) supersedes any previous confidence about the build or programming envelope. Its decision is **NO-GO** for hardware programming.
