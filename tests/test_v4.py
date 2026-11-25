"""Offline checks for V4 source, emitted Thumb veneers, and Linux client."""
import copy
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from firmware import build_patch, build_v4
from tools import rgb_effects, rgb_v4
from tools.recovery import recover_usb

ROOT = Path(__file__).resolve().parents[1]
STOCK = ROOT / "recovery_backup/vendor_v1.16.bin"
TOOLCHAIN = ("clang", "ld.lld", "llvm-objcopy", "arm-none-eabi-objdump", "arm-none-eabi-nm")


class ThumbVeneers:
    """Execute the emitted Thumb subset used by the assembly veneers.

    C bodies and stock branch targets are stubs. C logic executes separately
    in the native harness using the same production source.
    """

    def __init__(self, image):
        self.image = image
        self.registers = [0x11110000 + i for i in range(16)]
        self.registers[13] = 0x20000700
        self.registers[14] = 0x8E97
        self.ram = {0x200027B2: 1}
        self.zero = False
        self.min_sp = self.registers[13]

    def read(self, address, size):
        if address < len(self.image):
            return int.from_bytes(self.image[address:address+size], "little")
        return sum(self.ram.get(address+i, 0) << (8*i) for i in range(size))

    def write_word(self, address, value):
        self.ram.update((address+i, value >> (8*i) & 255) for i in range(4))

    def run(self, start, calls, stops):
        r = self.registers
        ip = start & ~1
        for _ in range(64):
            if ip in stops:
                return ip
            if ip in calls:
                if r[13] % 8:
                    raise AssertionError("Unaligned SP at C boundary")
                calls[ip](r)
                ip = r[14] & ~1
                continue
            word = self.read(ip, 2)
            next_ip = ip + 2
            if word & 0xFE00 in (0xB400, 0xBC00):
                regs = [i for i in range(8) if word & (1 << i)]
                if word & 256:
                    if word & 0x0800:
                        raise AssertionError("Unexpected POP PC in tested veneer")
                    regs.append(14)
                if word & 0x0800:
                    for register in regs:
                        r[register] = self.read(r[13], 4)
                        r[13] += 4
                else:
                    r[13] -= 4 * len(regs)
                    self.min_sp = min(self.min_sp, r[13])
                    for index, register in enumerate(regs):
                        self.write_word(r[13] + index*4, r[register])
            elif word & 0xF800 == 0xF000:
                second = self.read(ip+2, 2)
                if second & 0xD000 != 0xD000:
                    raise AssertionError("Expected Thumb BL")
                sign = (word >> 10) & 1
                j1, j2 = (second >> 13) & 1, (second >> 11) & 1
                delta = ((sign << 24) | ((1 ^ (j1 ^ sign)) << 23) |
                         ((1 ^ (j2 ^ sign)) << 22) | ((word & 1023) << 12) |
                         ((second & 2047) << 1))
                if sign:
                    delta -= 1 << 25
                r[14] = (ip + 4) | 1
                next_ip = ip + 4 + delta
            elif word & 0xFF00 == 0x4600:
                r[(word & 7) | ((word >> 4) & 8)] = r[(word >> 3) & 15]
            elif word & 0xFF87 == 0x4700:
                target = r[(word >> 3) & 15]
                if not target & 1:
                    raise AssertionError("Branch left Thumb state")
                next_ip = target & ~1
            elif word & 0xF800 == 0x4800:
                r[(word >> 8) & 7] = self.read(((ip+4) & ~3) + 4*(word & 255), 4)
            elif word & 0xF800 == 0x7800:
                r[word & 7] = self.read(r[(word >> 3) & 7] + ((word >> 6) & 31), 1)
            elif word & 0xF800 == 0xA800:
                r[(word >> 8) & 7] = r[13] + 4*(word & 255)
            elif word & 0xFF80 == 0xB000:
                r[13] += 4*(word & 127)
            elif word & 0xF800 == 0x2800:
                self.zero = r[(word >> 8) & 7] == word & 255
            elif word & 0xFF00 == 0xD000:
                delta = struct.unpack("b", bytes([word & 255]))[0] * 2
                if self.zero:
                    next_ip = ip + 4 + delta
            else:
                raise AssertionError(f"Unsupported veneer instruction {word:04x} at {ip:04x}")
            ip = next_ip
        raise AssertionError("Veneer did not exit")


class FirmwareTests(unittest.TestCase):
    def test_actual_c_routines(self):
        if not shutil.which("cc"):
            self.skipTest("native C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "harness"
            subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror",
                            str(ROOT / "tests/v4_firmware_harness.c"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    @unittest.skipUnless(STOCK.exists() and all(shutil.which(x) for x in TOOLCHAIN),
                         "stock binary and Cortex-M0 toolchain required")
    def test_build_guards_and_emitted_veneers(self):
        original = STOCK.read_bytes()
        args = SimpleNamespace(clang="clang", objcopy="llvm-objcopy",
                               objdump="arm-none-eabi-objdump", nm="arm-none-eabi-nm")
        image, manifest, disassembly = build_v4.build_v4(original, args, build_patch.encode_bl)
        second = build_v4.build_v4(original, args, build_patch.encode_bl)
        self.assertEqual((image, manifest, disassembly), second)
        self.assertFalse(manifest["programming_authorized"])
        self.assertEqual(image[0x9646:0x964A], original[0x9646:0x964A])
        self.assertEqual(manifest["sram_address"] + manifest["sram_size"], 0x20002D20)
        self.assertEqual(struct.unpack_from("<I", image, 0xA4A8)[0], 0x2508)
        self.assertEqual(image[build_v4.BASE - 2:build_v4.BASE], b"\xff\xff")
        symbols = manifest["symbols"]
        for address in build_v4.HOOKS:
            corrupt = bytearray(original)
            corrupt[address] ^= 1
            with self.assertRaisesRegex(ValueError, "Stock bytes mismatch"):
                build_v4.make_patches(corrupt, symbols, len(image), build_patch.encode_bl)
        bad = copy.copy(symbols)
        bad["v4_main_hook"] += 1
        with self.assertRaisesRegex(ValueError, "Invalid Thumb"):
            build_v4.make_patches(original, bad, len(image), build_patch.encode_bl)
        with self.assertRaisesRegex(ValueError, "exact stock"):
            build_v4.build_v4(bytes(42942), args, build_patch.encode_bl)

        def clobber(regs):
            regs[:4] = [0xdead0000 + i for i in range(4)]
            regs[12] = 0x12345678

        for start, helper, stop, lr in ((0x8E92, "v4_supervise", 0x321C, 0x8E97),
                                        (0x5B2A, "v4_revoke", 0x8930, 0x5B2F),
                                        (0x52F8, "v4_tick", 0x5746, 0x52FD),
                                        (struct.unpack_from("<I", image, 0x9C)[0],
                                         "v4_usb_event", 0x9E00, 0xFFFFFFF9)):
            vm = ThumbVeneers(image)
            vm.registers[14] = lr
            if start == 0x5B2A:
                vm.registers[0] = 1
            incoming = vm.registers.copy()
            self.assertEqual(vm.run(start, {symbols[helper]: clobber}, {stop}), stop)
            self.assertEqual(vm.registers[4:12], incoming[4:12])
            self.assertEqual(vm.registers[13:15], incoming[13:15])
            if start == 0x5B2A:
                self.assertEqual(vm.registers[0], 1)

        for skip in (False, True):
            vm = ThumbVeneers(image)
            incoming = vm.registers.copy()

            def compose(regs):
                self.assertEqual(regs[0], incoming[13])
                clobber(regs)
                regs[0] = int(skip)

            stop = 0x3F8E if skip else 0x3B10
            self.assertEqual(vm.run(0x3B0C, {symbols["v4_compose"]: compose}, {stop}), stop)
            self.assertEqual(vm.registers[1:12], incoming[1:12])
            self.assertEqual(vm.registers[13], incoming[13])
            if not skip:
                self.assertEqual(vm.registers[0], 1)
            self.assertEqual(vm.min_sp, incoming[13] - 16)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "v3.bin"
            builder = ROOT / "firmware/build_patch.py"
            subprocess.run([sys.executable, str(builder), str(STOCK), "--version", "3",
                            "--output", str(output)], check=True, capture_output=True)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), recover_usb.V3.sha256)
            recover_usb.verify_image(original, recover_usb.STOCK)
            recover_usb.verify_image(output.read_bytes(), recover_usb.V3)
            with self.assertRaises(ValueError):
                recover_usb.verify_image(image, recover_usb.V3)
            with self.assertRaises(ValueError):
                recover_usb.verify_image(image, recover_usb.STOCK)
            result = subprocess.run([sys.executable, str(builder), str(STOCK), "--output",
                                     str(STOCK)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(STOCK.read_bytes(), original)


class FakeHID:
    def __init__(self):
        self.packets = []
        self.pending = None
        self.stale_once = True
        self.accepted = 0
        self.closed = False

    def write(self, data):
        self.packets.append(data)
        response = bytearray(data)
        response[5] = 1
        response[6] |= 128
        response[7] = 0
        response[14:62] = bytes(48)
        if data[6] in (rgb_v4.Op.COMMIT, rgb_v4.Op.CHUNK_COMMIT):
            self.accepted = struct.unpack_from("<H", data, 12)[0]
        struct.pack_into("<HHH", response, 18, self.accepted, 0, self.accepted)
        response[35] = 15
        struct.pack_into("<II", response, 36, 31, 0x01160001)
        response[44:50] = bytes((75,5,15,16,5,64))
        response[53] = data[7]
        self.pending = bytes(response)

    def read(self, _timeout):
        if self.stale_once:
            self.stale_once = False
            return bytes(64)
        if self.pending is None:
            raise TimeoutError()
        response, self.pending = self.pending, None
        return response

    def close(self):
        self.closed = True


class HostTests(unittest.TestCase):
    def test_transport_and_effects(self):
        transport = FakeHID()
        client = rgb_v4.RGBController(transport)
        self.assertEqual(client.capabilities().layout, 0x01160001)
        client.external(lease_ms=1000, overlays=4)
        self.assertEqual(client.brightness(0).status, rgb_v4.Status.OK)
        self.assertEqual(client.brightness(65535).status, rgb_v4.Status.OK)
        self.assertEqual(client.overlays(3).status, rgb_v4.Status.OK)
        self.assertEqual(client.keepalive().status, rgb_v4.Status.OK)
        with self.assertRaises(ValueError):
            client.set_key(5, 0, (1,2,3))
        with self.assertRaises(ValueError):
            client.set_key(0, 15, (1,2,3))
        with self.assertRaises(ValueError):
            client.set_frame(bytes(224))
        self.assertEqual(client.set_key(4, 14, (1,2,3)).accepted, 1)
        self.assertEqual(client.frame[-3:], bytes((1,2,3)))
        n = len(transport.packets)
        gradient = rgb_effects.gradient((255,0,0),(0,0,255))
        self.assertEqual(len(gradient), 225)
        self.assertEqual(client.set_frame(gradient, fast=True).accepted, 2)
        self.assertEqual(len(transport.packets)-n, 5)
        self.assertEqual(client.wait_displayed().displayed, 2)
        self.assertEqual(len(rgb_effects.rainbow(0.4)), 225)
        client.seq = 65535
        with self.assertRaisesRegex(rgb_v4.RGBError, "exhausted"):
            client.set_frame(gradient)
        client.close()
        self.assertTrue(transport.closed)
        self.assertEqual(transport.packets[-1][6], rgb_v4.Op.MODE)
        self.assertEqual(transport.packets[-1][7], 0)

    def test_lost_commit_reply_preserves_per_key_updates(self):
        class LostReply(FakeHID):
            drop_commit = True

            def write(self, data):
                super().write(data)
                if data[6] == rgb_v4.Op.COMMIT and self.drop_commit:
                    self.drop_commit = False
                    self.pending = None

        transport = LostReply()
        client = rgb_v4.RGBController(transport, retries=1)
        client.external()
        with self.assertRaises(TimeoutError):
            client.set_key(0, 0, (1, 2, 3))
        self.assertEqual(client.set_key(0, 1, (4, 5, 6)).accepted, 2)
        self.assertEqual(client.frame[:6], bytes((1, 2, 3, 4, 5, 6)))
        client.close()

    def test_no_protocol_and_disconnect(self):
        class Silent(FakeHID):
            def read(self, _timeout):
                raise TimeoutError()
        class Disconnected(FakeHID):
            def write(self, _data):
                raise OSError("unplugged")
        with self.assertRaises(rgb_v4.UnsupportedProtocol):
            rgb_v4.RGBController(Silent()).capabilities()
        with self.assertRaises(rgb_v4.ConnectionLost):
            rgb_v4.RGBController(Disconnected()).capabilities()
