"""Build and independently disassemble the V4 extension for offline use."""
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

BASE = 0xA7C0
LIMIT = BASE + 8192
SRAM = 0x20002820
SIZE = 1280
# Stock V1.16 only. Vector and scatter length use little-endian words.
HOOKS = {
    0x009C: ("019e0000", "v4_irq_hook", "vector"),
    0x3B0C: ("b948807a", "v4_compose_hook", "bl"),
    0x52F8: ("00f025fa", "v4_tick_hook", "bl"),
    0x5B2A: ("02f001ff", "v4_reset_hook", "bl"),
    0x8E92: ("faf7c3f9", "v4_main_hook", "bl"),
    0x8E96: ("00f0d1fb", "v4_vendor_hook", "bl"),
    0x964A: ("00f060fc", "v4_stock_reply", "bl"),
    0x9ED8: ("00f025f8", "v4_out_hook", "bl"),
    0xA4A8: ("08200000", None, "zero-length"),
}


def run(*args):
    return subprocess.check_output(args, text=True)


def thumb(path, objdump, start, stop, *, raw=False):
    options = ("-D", "-b", "binary", "-m", "arm", "-Mforce-thumb") if raw else ("-d",)
    return run(objdump, *options, f"--start-address={start}", f"--stop-address={stop}", str(path))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def make_patches(original, symbols, end, encode_bl):
    patches = []
    for address, (expected, name, kind) in sorted(HOOKS.items()):
        old = bytes.fromhex(expected)
        require(address % 2 == 0 and address + len(old) <= len(original),
                f"Invalid patch location 0x{address:X}")
        require(not patches or address >= patches[-1][0] + len(patches[-1][1]),
                f"Overlapping patch 0x{address:X}")
        require(original[address:address + len(old)] == old,
                f"Stock bytes mismatch at 0x{address:X}")
        target = symbols.get(name) if name else None
        if name:
            require(target is not None and BASE <= target < end and target % 2 == 0,
                    f"Invalid Thumb destination {name}")
        if kind == "bl":
            require(-0x400000 <= target - (address + 4) <= 0x3FFFFE, "Thumb BL range")
            replacement = encode_bl(address, target)
        elif kind == "vector":
            require(address % 4 == 0, "Unaligned vector")
            replacement = struct.pack("<I", target | 1)
        else:
            require(struct.unpack_from("<I", original, address + 4)[0] == 0x20000818,
                    "Stock scatter destination mismatch")
            replacement = struct.pack("<I", SRAM + SIZE - 0x20000818)
        patches.append((address, old, replacement, name, target, kind))
    return patches


def build_v4(original, args, encode_bl):
    require(len(original) == 42942 and hashlib.sha256(original).hexdigest() ==
            "966742624d64e5d6de7efed1dc10ff7e080f5e99298397409cfb5264b5568844",
            "V4 requires exact stock V1.16")
    require(original[0x9646:0x964A] == bytes.fromhex("00f005f8"), "Stock recovery hook mismatch")
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        code, asm, elf, raw = (temp / name for name in ("code.o", "veneer.o", "firmware.elf", "code.bin"))
        flags = ("--target=armv6m-none-eabi", "-mcpu=cortex-m0", "-mthumb")
        run(args.clang, *flags, "-Oz", "-ffreestanding", "-fno-builtin",
            "-fstack-usage", "-c", str(source / "v4.c"), "-o", str(code))
        run(args.clang, *flags, "-c", str(source / "v4.S"), "-o", str(asm))
        run(args.clang, *flags, "-nostdlib", "-fuse-ld=lld", "-Wl,--build-id=none",
            f"-Wl,-T,{source / 'v4.ld'}", str(asm), str(code), "-o", str(elf))
        run(args.objcopy, "-O", "binary", "--only-section=.text", str(elf), str(raw))
        payload = raw.read_bytes()
        end = BASE + len(payload)
        require(BASE % 4 == 0 and len(original) <= BASE < end <= LIMIT, "V4 flash envelope exceeded")
        require(SRAM + SIZE <= 0x20005000 and SRAM % 8 == 0, "V4 SRAM envelope")
        functions = {row[-1] for line in run(args.objdump, "-t", str(elf)).splitlines()
                     if len(row := line.split()) == 6 and row[2:4] == ["F", ".text"]}
        symbols = {}
        for line in run(args.nm, "--defined-only", str(elf)).splitlines():
            address, kind, name = line.split()
            if kind in ("t", "T") and name in functions:
                symbols[name] = int(address, 16)
        patches = make_patches(original, symbols, end, encode_bl)
        assembly = thumb(elf, args.objdump, BASE, end)
        stack = {}
        for row in code.with_suffix(".su").read_text().splitlines():
            location, count, storage = row.split("\t")
            require(storage == "static", f"Unbounded V4 stack at {location}")
            stack[location.rsplit(":", 1)[-1]] = int(count)
        require(max(stack.values()) <= 64, "V4 local stack budget exceeded")
        require(all(f"<{name}>:" in assembly for name in symbols), "Missing injected function listing")

        output = bytearray(original)
        output.extend(b"\xff" * (BASE - len(output)))
        output.extend(payload)
        manifest_rows = []
        stock_file = temp / "stock.bin"
        stock_file.write_bytes(original)
        for address, old, new, name, target, kind in patches:
            output[address:address+len(old)] = new
            manifest_rows.append(dict(address=address, stock=old.hex(), replacement=new.hex(),
                                      target=target, symbol=name, kind=kind))
        generated = temp / "patched.bin"
        generated.write_bytes(output)
        # Verify branch destinations using GNU objdump's decoder on the generated raw image.
        for row in manifest_rows:
            address, target = row["address"], row["target"]
            kind = row["kind"]
            if kind == "bl":
                before = thumb(stock_file, args.objdump, address, address + 4, raw=True)
                after = thumb(generated, args.objdump, address, address + 4, raw=True)
                match = re.search(r"\bbl\s+(?:0x)?([0-9a-f]+)\b", after)
                require(match and int(match[1], 16) == target, f"Disassembler branch mismatch {address:#x}")
                row["stock_disassembly"] = "\n".join(line.strip() for line in before.splitlines() if re.match(r"^\s*[0-9a-f]+:", line))
                row["replacement_disassembly"] = after.splitlines()[-1].strip()
            elif kind == "vector":
                require(struct.unpack_from("<I", output, address)[0] == target | 1, "Vector mismatch")
            else:
                require(struct.unpack_from("<I", output, address)[0] == 0x2508, "Scatter length mismatch")
        # Disassemble the injected functions from the actual generated image.
        # Preserve ELF mapping symbols so embedded literal pools remain data.
        raw.write_bytes(output[BASE:end])
        replay = temp / "verify.elf"
        run(args.objcopy, "--update-section", f".text={raw}", str(elf), str(replay))
        decoded = thumb(replay, args.objdump, BASE, end)
        require(decoded.splitlines()[2:] == assembly.splitlines()[2:],
                "Raw injected instructions differ from the linked ELF")
        tabular_instructions = (
            re.match(r"^\s*([0-9a-f]+):\t[0-9a-f]{4}(?: [0-9a-f]{4})? *\t([a-z][a-z0-9.]*)\s*(.*)", line)
            for line in assembly.splitlines()
        )
        instructions = {int(row[1], 16): (row[2], row[3])
                        for row in tabular_instructions if row}
        require(all(target in instructions for target in symbols.values()),
                "Injected symbol is not an instruction boundary")
        branches = 0
        for address, (op, operands) in instructions.items():
            mnemonic = op.split(".", 1)[0]
            if mnemonic == "bl" or mnemonic in (
                "b", "beq", "bne", "bcs", "bcc", "bhs", "blo", "bmi", "bpl",
                "bvs", "bvc", "bhi", "bls", "bge", "blt", "bgt", "ble", "cbz", "cbnz",
            ):
                destination = re.search(r"(?:^|,\s*)([0-9a-f]+)\s+<", operands)
                require(destination and int(destination[1], 16) in instructions,
                        f"Injected direct branch at {address:#x} misses an instruction boundary")
                if mnemonic == "bl":
                    require(int(destination[1], 16) in symbols.values(), "Unresolved injected direct BL")
                branches += 1
        permitted = {address + i for address, old, *_ in patches for i in range(len(old))}
        require(all(a == b or i in permitted for i, (a, b) in enumerate(zip(original, output))),
                "Unexpected stock byte modification")

    return bytes(output), dict(
        version=4, stock_sha256=hashlib.sha256(original).hexdigest(),
        sha256=hashlib.sha256(output).hexdigest(), length=len(output),
        extension_address=BASE, extension_size=len(payload), offline_flash_limit=LIMIT,
        sram_address=SRAM, sram_size=SIZE, stack_local_bytes=stack,
        hooks=manifest_rows, symbols=symbols, verified_direct_branches=branches,
        programming_authorized=False,
    ), assembly.replace(str(elf), "v4-extension.elf")


def write_v4(original, args, encode_bl):
    image, manifest, assembly = build_v4(original, args, encode_bl)
    outputs = (args.output, args.manifest or args.output.with_suffix(".manifest.json"),
               args.output.with_suffix(".disasm"))
    require(len({p.resolve() for p in outputs}) == 3, "Output paths must be distinct")
    require(all(not p.exists() for p in outputs), "Outputs already exist")
    for path, data in zip(outputs, (image, (json.dumps(manifest, indent=2) + "\n").encode(),
                                    assembly.encode())):
        with path.open("xb") as f:
            f.write(data)
    print(json.dumps({k: manifest[k] for k in ("sha256", "length", "extension_size", "sram_size")}))
    for hook in manifest["hooks"]:
        print(f'{hook["address"]:#06x}  {hook["stock"]} -> {hook["replacement"]}  '
              f'{hook.get("replacement_disassembly", hook["kind"])}')
    print("Offline candidate:", *outputs)
