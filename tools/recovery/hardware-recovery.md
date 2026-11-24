# Hardware recovery — Ducky One 3 SF RGB

Status: planned; no hardware programmer or full flash backup has been tested.

## Before connecting

- Obtain a programmer explicitly supporting NUC1261SG4AE flash programming and verify exact device support in the programmer software. Generic SWD support alone does not guarantee flash support.
- Obtain the exact MCU datasheet and technical reference manual. Photograph both PCB sides and identify ICE_DAT/SWDIO, ICE_CLK/SWCLK, nRESET, ground and target voltage reference by continuity with power disconnected.
- Verify voltage and programmer pinout. Avoid dual power sources; do not connect a programmer power output to an already powered board.
- Keep the original V1.16 updater and extracted image offline. The expected extracted image is 42942 bytes, SHA-256 `966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844`.

## Establish access without erasing

On Gentoo, optionally install OpenOCD (`sudo emerge --ask dev-embedded/openocd`). Inspect installed interface and target configurations with `find /usr/share/openocd -iname '*numicro*'`. Confirm exact chip support and flash bank mapping before using it; otherwise use the official Nuvoton ICP tool on a supported host. Disable automatic unlock/erase options. Connect at low SWD clock speed, halt the target, and read device identity and protection status. If ordinary attach fails, investigate connect-under-reset. Unlocking protected flash may erase its contents. Do not unlock or mass erase a protected chip to obtain a backup.

Verified V1.16 USB identity: MCU product ID `0x01205212`, LDROM version `0x33`, CONFIG0 `0xF7FFFF7C`, CONFIG1 `0x00033200`. Recheck independently; these are not universal configuration values.

## Backup checklist

Record programmer/software versions, board revision, device identity, flash sizes, addresses, protection settings and boot selection. Read each accessible region twice, compare independent dumps byte-for-byte and preserve logs. Do not assume generic NuMicro memory sizes or bank numbers.

- Full APROM, including bytes beyond the vendor updater image. Current APROM may contain the V3 patch; label it accordingly, not as factory firmware.
- Full LDROM (original Ducky bootloader).
- Data Flash and any separate persistent settings regions; record overlap with APROM if applicable.
- All configuration words and accessible protected storage (SPROM if implemented and readable).
- Device identifiers and other readable factory information for reference, not for rewriting.
- Record unreadable regions explicitly. SRAM is volatile and is not required for persistent recovery.

Use `cmp` for each pair of dumps and `sha256sum` for a manifest. Store at least two offline copies. Never publish proprietary dumps or device-specific secrets. A checksum proves integrity, not correctness or completeness. Check for suspicious all-zero/all-FF dumps and compare APROM with the known image where appropriate.

## Recovery procedure (after verified backups)

1. Identify the target and verify backup hashes, region sizes and addresses.
2. Prefer APROM-only recovery first. Preserve LDROM, configuration and persistent settings unless demonstrably damaged.
3. Use the verified chip-specific programmer to erase/program only the intended region, then read back and compare. If restoring a full backup, use its recorded layout, not guessed addresses.
4. Restore LDROM or Data Flash only if required and backed up. Restore configuration last using documented masks and boot settings; avoid irreversible security changes. Do not write factory identifiers.
5. Reset, verify USB enumeration, typing, lighting and bootloader access. Preserve logs.
6. Validate independent recovery access and verified backups before any destructive tests. No independent recovery procedure has been demonstrated.

## Remaining development

Implement backup_flash.py and recover_swd.py only after confirming the programmer, chip support, memory layout and protection behavior. Require explicit confirmation, exact identity, region-level allowlists and readback verification. Never silently mass erase. If protected memory cannot be backed up, full recovery remains unproven. Physical damage and some security states may be unrecoverable.
