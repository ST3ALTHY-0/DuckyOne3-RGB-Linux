# Framebuffers and LED coordinates

## Formats and ownership

| SRAM region | Format and ownership | Evidence |
|---|---|---|
| `0x20001770–0x20001931` | Native RGB16 work frame, 75 triplets, 450 bytes | `0x3176` literal load, `0x317A–0x3192` index and stores |
| `0x20001BD0–0x20001D91` | RGB16 native effect scratch, same geometry | Cleared through literal `0x2414` at `0x2332–0x233E`. Per-pixel rates in `0x68C` and `0x888` |
| `0x20001D94–0x20001F55` | Alternate RGB16 source used by configuration/preview | `0x3578 → 0x3B08`. `0x2364` fills a hue gradient with halfword stores at `0x23BC–0x2402`. `0x2C9C` samples it with halfword reads at `0x2D38/0x2D76/0x2DB2` |
| `0x20001364–0x20001491` | Two 151-byte native profile records, one enable byte plus 75 little-endian RGB444 words each | `0x35A6`, `0x3B08` record stride `0x97`, per-pixel word at +1 |
| `0x20000E18–0x20000FD9` | Composed scanout page 0, 450 bytes | `0x3B4C`, `0x3702` |
| `0x20000FDA–0x2000119B` | Composed scanout page 1, 450 bytes | `0x3B0C–0x3B62`, `0x3702–0x372A` |
| `0x20002438–0x20002482` | Native per-position state, 75 bytes | `0x2340–0x234A` fills with 2, `0x2C9C` updates from key events |

**High.** For the RGB16 grids, offset = `bank*0x5A + index*6`. RGB are consecutive little-endian halfwords at offsets 0, 2, 4. A bank has 15 positions. A grid has five banks. These grids represent addressable slots. Physical key names, spare slots, and shared legends are separate mapping data.

## Two coordinate translations

**High.** `0x3160` calls `0x4BE2` with direction 1 at `0x3170`. `0x4BE2` uses `LDRH` at `0x4BFE/0x4C1E`, four records at stride 4, and matches the low 16-bit coordinate `(bank<<8)|index`. Direction 0 searches column 0 and returns column 1. Direction 1 searches the reverse. A miss at `0x4C2C` returns the original word. Startup data at `0xA54E` expands into SRAM. Bytes at offset `0x2E0` independently decoded from the image are:

```
04 04 03 04   03 04 04 04   07 04 06 04   06 04 07 04
```

This swaps bank 4 indices 3↔4 and 6↔7 in either direction. `0x3B08` uses the same four records at `0x3CDE` and `0x3D54` for a second mapping step when writing the output. The main 75-slot copy is followed by rewriting those four destinations. With profiles and indicators disabled, encoding a host pixel using the same work-coordinate mapping as `0x3160` preserves V3 logical coordinate semantics through the compositor. A direct scanout-page writer would need to reproduce the combined mapping.

## Composition and brightness

**High.** `0x3B08` takes base pixels in `r0`, flags in `r1/r3`, and profile base, per-profile control records, and count in three stack arguments. Verify the full ABI at `0x3542–0x3556`. The visible color is the first enabled profile with a nonzero packed RGB444 word, or the source triplet copied verbatim with `0x41A8`. Palette data starts at `0x20001496`. `0x2E2E` changes native palette channel indices and another bounded channel setting, then calls `0x241C` to derive effect parameters. For a nonzero component with active fade, the compositor computes `palette[n] - step*floor(palette[n]/divisor)`; divisor is selected from `0x200014AC + 2*selector`, selector at `0x200014C8`. Division is `0x4008`. Base pixels have no compositor-wide brightness adjustment. V3 expands RGB8 via `n*257` before writing the work frame.

**High.** `0x3EEC–0x3F34` can copy the active page's pixel at byte offset `0x186` to four slots in the back page. `0x3F38–0x3F86` can force a white pixel and three single-channel indicator pixels. V4's pure external path should pass zero profile count and zero override flags. An indicator-preserving mode can be added explicitly once product semantics are mapped.

## Publication contract

**High.** `0x3B08` chooses page `active XOR 1` at entry and signals pending only at `0x3F8C` after writing the complete page. `0x3A18` consumes pending at the next bank-zero start and toggles the active index. The ISR never directly reads the native effect work frame. With one foreground producer and pending clear before it starts, the ISR has no reason to toggle active while that producer is filling the back page. Never compose into an already-pending page. A suspend/flash transition can invalidate the frame or delay publication and should be handled as a separate lifecycle event. [Driver state](led-driver.md)

## Preimplementation writer and overlay audit

**Scanout pages.** The ordinary writer uses `0x41A8` and direct stores under `0x3B08`. The stock copy helper has 17 direct BL witnesses in the raw Thumb listing. Eight under `0x3B08` write/read composed data. Four at `0x083A/0x0848/0x0856/0x0864` and four at `0x0D94/0x0DA2/0x0DB0/0x0DBE` replicate special slots in the native work frame. One at `0x63F0` compacts key records, using the `0x20001A08` workspace supplied at `0x8C48`. Its aligned copy implementation also appears as the direct target `0x41D0` for stack-table initialization and USB replies. The only resolved runtime bulk clear of both pages is `0x3AC2 → 0x53BC`. Its three callers are `0x37A0`, `0x3914`, and `0x39CC`. Stock scatter zeroing precedes those. `0x3F92` blanks via state/GPIO and the ISR substitutes zero local values. `0x3660` and `0x3A18` read pixels and update state, with no resolved writes to either page. Confirm no hidden aliases during the release trace.

**Native work frame.** The [function map](function-map.md) identifies direct and indirect producers, including the clear-and-restore at `0x313C`, remap/write at `0x3160`, preview/configuration writers, init/tick function pointers, and software-timer callback `0x5B0C`. A compositor input shim leaves those writers and the alternate gradient intact. They can change native compositor flags or records. Source substitution and explicit overlay masking prevent them replacing external colors. Stock suspend/resume clears both physical pages by design.

**Extension region.** Only a future modified scatter descriptor, the private IRQ mailbox/control state, and V4 foreground storage/publisher should write the reservation. Stock indirect memory closure is unresolved, so record the region as a conditional allocation. In the proposed firmware, the single V4 producer owns the back page only while pending is clear. Frame commit and generation metadata are foreground-owned.

| Replacement | Verified trigger and destination | V4 policy |
|---|---|---|
| Alternate RGB16 input | Stock call at `0x357A` selects `0x20001D94` when preview/edit state requests it | Substitute external source in all five calls at the common prologue |
| Profile overlay words | Two records at `0x20001364`, controls from stock call sites, first enabled nonzero RGB444 wins. Repeated for remapped destinations at `0x3CDE–0x3D28` | Independent profile allow bits. Use stock enables/step values and priority |
| Prior-page replication | Enabled profile word at offset `0x83` triggers `0x3EEC–0x3F34`. Copy the active-page slot 65 (bank 4, index 5) to slots 63, 64, 66 and 67 | Part of profile overlay capability. To disable independently would require separating the stock compositor branch |
| Caps Lock white | Stock r1 bit 1 at `0x3F38–0x3F58` writes `FFFF FFFF FFFF` at offset `0xB4`, bank 2 index 0. IRQ `0x9EC4 → 0x2BDE` writes host LED bits at `0x20002670`. The decoded keyboard HID report descriptor at SRAM offset `0xC5` declares Num, Caps and Scroll usages | Bit 0 allow. Caps Lock typing and host reporting remain functional when disabled. The decoded default key table confirms Caps Lock (HID usage 0x39) at offset `0x1E`. No dedicated Num/Scroll pixel overwrite is resolved in this compositor |
| Three marker slots | Nonzero saved r3 at `0x3F5A–0x3F86` writes full R, G, B respectively to bank 3 indices 2, 3, 4. Scheduler `0x3510–0x3538` derives it from discriminator 3 and effect ID 6,7,8,9,10,11 | Bit 1 allow the stock group as-is. Startup key table `0x2000002F–0x20000031` decodes to HID Z, X, C. The manual describes the corresponding RGB channel adjustment keys. Verify that each physical LED follows its logical label on the target |
| Blanking and lifecycle | State +9 at `0x3700` path zeroes outgoing data, suspend/resume or init clears via `0x3AC2` | Preserve in every mode. This is output lifecycle, independent of overlay flags |

The four remap destinations use the other column of the same permutation. This is address translation. It applies with the overlay mask zero.

Ducky documents two concurrent custom lighting zones, CM1 and CM2, with CM1 first when zones overlap. This matches the first-enabled profile priority and fade controls in the stock compositor. Treat these as zone overlays, separate from keyboard macro profiles. [Ducky One 3 SF manual, RGB LED zone customization](https://cdn.shopify.com/s/files/1/0728/4382/1295/files/Ducky_One3_SF_usermanual_V9_EN_only_20240312_9deb8208-80f2-4975-a0ea-cb6442138e85.pdf?v=1741246316#page=8)
