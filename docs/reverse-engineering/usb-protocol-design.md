# V4 vendor HID transport

The normative packet layouts, opcodes, error values, session state and handoff rules are in the [V4 implementation specification](v4-implementation-spec.md#exact-vendor-hid-v1-format).

## Stock transport evidence

- Decoded endpoint descriptors at `0x200001AB` and `0x200001B2` describe IN `0x81` and OUT `0x02`, 64 bytes each, one full-speed USB frame between poll opportunities. The vendor collection is `0xFF00` usage 1, with no report ID. Linux hidraw adds a zero report ID outside the 64-byte payload. [Existing HID notes](../hid-protocol.md)
- `0x9ED8 → 0x9F26` copies 64 bytes from `0x40060100 + BUFSEG` into `0x2000254C` and sets `0x2000269F` before rearm. `0x963C` consumes the flag, calls `0x9654`, sends `0x2000258C` via `0x9F0E` and clears ready. A new receive can race that ready clear. One shared byte is insufficient to count incoming reports.
- `0x40060534` returns actual OUT length until written to rearm. The V4 shim checks length before invoking stock or publishing a private mailbox. Recognized V4 payloads never flow into the stock mailbox. Stock full-length vendor traffic keeps its handler, including bootloader entry. The V4 foreground hook is `0x8E96`. `0x9646`, the V3 hook, remains stock in a V4 image built from the original. [NUC1261 USBD endpoint definition](https://raw.githubusercontent.com/OpenNuvoton/NUC1261BSP/master/Library/Device/Nuvoton/NUC1261/Include/NUC1261.h#L14560)
- `0x9654` requires payload byte 1 = `0x3A`, byte 4 = 1, and recognizes subcommands 1 and 4 at byte 5. V3's exact custom prefix also has byte 4 equal to 1. The V4 prefix `00 3A 52 34 E4` therefore has no overlap on this interface.

## Throughput assumptions

| Transfer | Approximate frames/s at one complete exchange per ms | At two ms per exchange |
|---|---:|---:|
| V3 75 single-pixel OUT reports | 13.3 theoretical before host overhead | 6.7 |
| V4 five chunks plus explicit commit | 167 | 83 |
| V4 optional final-chunk commit | 200 | 100 |
| Physical scan | ~300 nominal full scans/s from TIMER1 | Independent of USB |

These are static ceilings. Host turnaround, burst behavior, dropped or stale replies and row busy skips reduce effective performance. Keep one outstanding transaction, match session, opcode, frame sequence and request tag, and retry idempotently. USB transport success alone gives no application acceptance. Test stock IN interleavings, readiness after USB reset, and zero-length through oversized reports in an offline endpoint model first. Capture actual rates only during separately authorized validation. [Driver timing](led-driver.md)
