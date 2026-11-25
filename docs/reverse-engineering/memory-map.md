# V1.16 memory map

## Startup allocations

**High.** Vector word at `0x00` initializes MSP to `0x20000818`. The scatter walker at `0xA47C` iterates startup descriptors through `0xA4C4`. The descriptor at `0xA4A4` selects the zero routine at `0xA440`. Its payload is size `0x2008`, destination `0x20000818`, then a terminator. This reserves the whole zero-init region through `0x2000281F` inclusive. Holes in cross-references in this range carry no allocation guarantee.

**High.** The descriptor at `0xA4B4` selects `0x42D2`. The source is the argument-record address `0xA4B8 + 0x96 = 0xA54E`. The compressed length is `0x4E0 >> 1 = 0x270` and destination `0x20000000`. The observed stream produces `0x414` bytes through `0x20000413`. It includes key/config tables, USB descriptors, and the remap pairs. `0x20000414–0x20000817` is at most 1,028 bytes below initial MSP. This is an upper bound before hitting decoded initialized data. It is neither an allocation nor an observed stack watermark.

| Region | Use / evidence |
|---|---|
| `0x2000018B` vicinity | Decoded USB configuration descriptors, EP1 at `0x200001AB`, EP2 at `0x200001B2` |
| `0x200002E0–0x200002EF` | Four remap records, literals `0x4DD0/0x3FC4` |
| `0x20000818–0x2000281F` | Zero-init allocation, including the 1,536-byte profile/macro workspace at `0x20000818–0x20000E17` initialized to 0xFF via `0x59C0 → 0x539C` |
| `0x20000E18–0x2000119B` | Two contiguous 450-byte composed pages |
| `0x2000119C`, `0x20001234`, `0x200012CC` | Profile/configuration objects accessed through `0x4904/0x493A/0x4974` |
| `0x20001364–0x20001491`, `0x20001494` onward | Profile overlay arrays and lighting options |
| `0x20001770–0x20001931`, `0x20001934–0x200019C3` | Native RGB16 work grid and dispatch table |
| `0x20001BD0–0x20001D91`, `0x20001D94–0x20001F55` | Native RGB16 scratch and alternate work grids |
| `0x20001F58–0x20002119` | 75 six-byte keyboard scan/debounce records, literal `0x4DC4` |
| `0x2000211C–0x20002247` | Capacity for 75 four-byte key event records, literal `0x4DE4` |
| `0x20002348–0x200023E7` | 20 eight-byte keyboard GPIO descriptors, `0x4A1C` and literal `0x4DE0` |
| `0x20002438–0x20002482` | Reactive state grid |
| `0x2000254C–0x2000258B`, `0x2000258C–0x200025CB` | Vendor RX and TX mailboxes |
| `0x200025CC–0x20002607` | Five 12-byte GPIO row descriptors, initialized at `0x3838–0x3870` |
| `0x20002640`, `0x20002670`, `0x2000269E/9F` | Native effect, lighting service, validation and USB ready state |
| `0x200027A8` onward | Driver state, including ready/active/pending bytes at `0x200027B0/B2/B3` |
| `0x200027E0`, `0x200027EC`, `0x20002808` | Scan dispatch, USB/lifecycle state, software timer list |

## Stack and interrupts

**High.** Lighting service `0x321C` pushes 20 bytes and subtracts 28. Compositor `0x3B08` adds 64 bytes of its own frame (20+44), yielding 112 bytes for that pair before leaf calls and callers. SPI ISR `0x3660` pushes 24 bytes. Cortex-M0 exception entry stacks eight words, so an SPI IRQ takes at least 56 bytes while preempting foreground code. TIMER and USB bring their own frames and may nest according to NVIC priorities. Mode 10 has another 100-byte local frame, from its five-register save and 80-byte stack adjustment. It runs below the 48-byte lighting service frame. All five non-default external vectors are identified in the driver notes. There is no measured worst case. Flash jobs, effects with large local frames, USB events, and nested IRQs must be included when establishing a V4 stack budget. See [LED driver](led-driver.md) for mapped vectors.

**Potential allocation, unapproved.** The NUC1261 series part table gives 20 KiB SRAM for the supplied model. This suggests the upper address band beginning at `0x20002820` is worth auditing, subject to confirmation of the MCU and revision. That is 10,208 physical bytes to the nominal SRAM end `0x20005000`. A PC-relative literal scan found zero direct upper-band loads. An aligned raw word scan found ten candidate values, each arising from pairs of Thumb instructions. These scans cannot exclude computed addresses. Before choosing V4 storage, audit pointer derivation, function tables, startup and reset paths, copies from NVM, USB and peripheral use, and any region sizing or RAM aliasing. The design needs about 0.5–0.9 KiB depending on retained precision and staging strategy. Require explicit bounds, alignment and initialization. [Nuvoton model specifications](https://www.nuvoton.com/export/sites/nuvoton/files/product-related-information/NuvotonPSG.pdf)

## Flash

**High.** Loaded APROM occupies `0x0000–0xA7BD`, including initialized compressed bytes through the end. V3 aligns its appended dispatcher to `0xA7C0` and changes the four bytes at `0x9646`; see [build_patch.py](../../firmware/build_patch.py). The physical flash size and an image append point give different constraints. Existing stock FMC accesses use the ISP registers and flash job machinery, for example `0x4350`, `0x4440`, and `0x53F8`. Preserve all known native flash uses, bootloader boundaries, update envelope, page checks and stock restore. The verified recovery profile records CONFIG1 `0x00033200`. Static persistent-storage code includes `0x33200` at `0x9100`, settings pages selected by `0x4804`, and a 16-byte validation read from `0x3F800` at `0x93DC`. `0x43E8` may apply a `0x20000` address offset on another detected profile. Treat `0x33200` as a candidate data-flash boundary for the tested identity. The updater envelope and usable V4 extension budget remain open. [Repository storage findings](../firmware.md)

## V4 preimplementation audit

**Physical SRAM.** The specific NUC1261SG4AE has one 20 KiB IRAM allocation. The family memory organization maps it from `0x20000000` through `0x20004FFF`, inclusive. The software boundary is `0x20005000` exclusive. This is distinct from the USBD packet aperture. The working board identity still comes from the existing verified recovery profile. [Exact NUC1261SG4AE CMSIS device-pack memory entry](https://raw.githubusercontent.com/OpenNuvoton/cmsis-packs/master/Nuvoton_DFP/Nuvoton.NuMicroM0_DFP.pdsc#L5485-L5493)

### Static and computed destinations

| Writer family | Resolved destinations and bounds |
|---|---|
| Startup `0xA440` and `0x42D2` | Stock zero descriptor at `0xA4A8` covers `[0x20000818,0x20002820)`. Known decompression source `[0xA54E,0xA7BE)` produces `[0x20000000,0x20000414)`. The source output was independently decoded |
| Firmware stack | Initial MSP `0x20000818`. PUSH and exception entry move down from it. Read-only scans found no normal-path alternate SP initialization. HardFault wrapper `0xA2C8/0xA2D8` selects MSP or PSP for diagnostics. Stack is outside the upper reservation and may still overflow into lower initialized data |
| Application allocations | Stock work/scratch/settings, key records, lighting and callback structures sit within zero-init. Examples include macro/profile block reset `0x59C0 → 0x539C` with length `0x600`, selected configuration copy paths around `0x8F00`, and stock profile scratch fill `0x9326` to `0x2000119C`, length 456 |
| Dynamic callback/timer lists | `0x56EC` inserts caller-supplied timer records and `0x57D6` dispatches a stored callback; known records such as `0x20002754` are static SRAM objects. Scan dispatch `0x4D96–0x4DAA` targets `0x8BDC` via `0x200027E4`. No general allocator was identified. Unresolved callbacks and corruption paths remain open |
| Key report compaction | `0x8C48 → 0x63D8 → 0x63F0 → 0x41A8` shifts six-byte entries within the key-report workspace from param base `0x20001A08`, indexed by its count. This write is distinct from the lighting store even though both use stride six |
| USB | CPU mailboxes at `0x2000254C/0x2000258C`. SETUP/control state at `0x200002FC`, max observed indexed state field +0x48. Device endpoint buffer addresses are derived from `0x40060100 + BUFSEG`. `0x9F64–0x9FB0` assigns setup offset 0, control slots at 8, and endpoint slots at 16, 80, 144, 152, 156 and 220. The vendor transfers at 16/80 are 64 bytes. All stay in peripheral packet SRAM. `0x9DC4` copies CPU-side, and USB IRQ SETUP uses a fixed 8-byte copy |
| SPI/PWM/PDMA | `0x3A18` and `0x3660` read active frame by CPU and write SPI TX directly. No PDMA vector beyond the default handler, no aligned literal in the PDMA aperture `[0x50008000,0x5000C000)`, and startup clock module enables at `0x94CE–0x9570` resolve to the used peripheral modules. SPI setup explicitly clears the DMA transmit enable path at `0x4E3E–0x4E44`. No PDMA lighting or USB SRAM destination was resolved. This is a static result |
| FMC and copies | FMC address registers select flash source/destination. CPU-side reads via `0x4674` resolve to known settings areas or stack locals. The zero/copy helpers take destination and byte count from callers. `0x53BC` direct sites `0x3ACC/0x767A/0x9326/0x9D82` are page clear, keyboard report clear, profile clear and USB control clear respectively |

The raw linear scan found ten aligned upper-SRAM-looking words. Each is a pair of Thumb instructions at `0x2E28/0x3050/0x49B0/0x5BF0/0x5C24/0x68DC/0x6AF8/0x81AC/0x98BC/0x990C`. Searches of actual PC-relative loads yielded no upper-SRAM destination. Flash content is not uniformly code. This audit uses the decoded startup descriptors to guard against reporting code bytes as pointers.

### Stack risk and reservation

The 1,028 bytes between MSP and the initialized data end give an absolute collision ceiling for normal downward growth, with no proven guard in stock. Examples of simultaneously live foreground frames are main 8 + scheduler 48 + mode 10 local frame 100 = 156 bytes, or main 8 + scheduler 48 + compositor 64 + aligned copy 12 = 132 bytes. The mode 10 sum excludes callees. Keyboard event processing starts with main 8 + scanner 24 + event callback 24, then can reach larger profile and flash helper frames. The stock `0x8930` and `0x7624` functions each use 96 bytes. A settings reset can hold main 8 + background timer 16 + reset callback 24 + `0x8930` 96 + `0x77AC` 16 = 160 bytes simultaneously. The USB standard SETUP path holds at least 24 (`0x9E00`) + 8 (`0x98BA`) + 24 (`0x9A3C`) software bytes, or 88 including basic exception entry before further callbacks. The setup IRQ alone can raise the reset-path witness to 248 bytes, with possible alignment and deeper children remaining. The SPI IRQ uses 24 software bytes plus 32 basic exception-frame bytes (allow up to four alignment bytes). TIMER1 uses 8 + 16 software bytes through `0x3A18`, plus at least 32 hardware bytes. USB uses 24 software bytes before its invoked functions and exception frame. These are path witnesses. They do not sum into a maximum.

The active vectored sources are TIMER1/2/3, SPI0 and USB. Static scanning found no literal addressing the NVIC priority registers or SHPR fields and no normal-path switch to PSP. Equal reset priorities imply no configurable IRQ nesting if the stock boot handoff and initialization leave priorities at reset. Without a live witness for that assumption, reserve for up to four distinct configurable priority levels plus possible fault entry and report any nesting seen. Use a stack watermark under key, profile and USB load. No supported stock worst-case stack measurement is available.

The V4 specification reserves `[0x20002820,0x20002D20)` by extending the exact startup clear descriptor. This is more defensible than borrowing a native scratch frame or the MSP gap. `0x2312` clears native scratch; preview, flash callbacks, macro workspaces and USB queues remain live during external mode. The explicit reservation is **statically justified for the resolved stock paths**. It remains conditional on dynamic alias and watermark evidence. Instrument writes to this full range and both scanout pages under stock firmware, and check that instrumentation exercises callback, profile and USB paths as well as boot. Do not describe the upper band as verified free until that check passes. Keep exact region sizes and release assertions in the [implementation specification](v4-implementation-spec.md).


### Implemented diagnostic strategy

The build extends the startup clear exactly through `0x20002D1F`. V4 sets canaries at source-page padding `0x20002901` and `0x200029E5`, the derived-frame tail halfword `0x20002BAA`, and reservation tail word `0x20002D1C`. Guard corruption or an inconsistent mode/index latches a fault and revokes external mode. The audited revision checks the frame selector at command and compositor use sites as well as in the supervisor. These samples cannot detect a clobber elsewhere in a buffer.

The generated-image Ghidra trace verified the precise zeroing extent, back-page writes, page selection, and vendor transaction without writes outside modeled SRAM and MMIO ranges. Hardware release still requires watching the full V4 range under the stock image and a stack watermark under overlapping keyboard, profile, LED and USB work. No V4 recovery profile has been added.

See the [independent hardware readiness report](v4-hardware-readiness.md) for revised candidate evidence, unresolved writer families and the non-destructive stack diagnostic.
