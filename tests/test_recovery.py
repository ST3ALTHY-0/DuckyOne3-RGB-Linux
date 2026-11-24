import contextlib
from dataclasses import replace
import hashlib
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from firmware import build_patch
from tools.recovery import inspect_ducky_ldrom as hid
from tools.recovery import recover_usb as recovery


class ProtocolTests(unittest.TestCase):
    def test_reboot_descriptors(self):
        cases = (
            ("05 01 09 00 A1 01 C0", "CC"),
            ("06 00 FF 09 01 A1 01 C0", "00 3A 01 09 01 04 00 01 01"),
            # Same usage expressed with a wider HID short item.
            ("07 00 FF 00 00 09 01 A1 01 C0", "00 3A 01 09 01 04 00 01 01"),
        )
        for descriptor, prefix in cases:
            with self.subTest(descriptor=descriptor):
                payload = hid.reboot_payload(bytes.fromhex(descriptor))
                self.assertEqual(payload, bytes.fromhex(prefix).ljust(64, b"\0"))
                with patch.object(hid.os, "write", return_value=65) as write:
                    hid.write_report(7, payload)
                write.assert_called_once_with(7, b"\0" + payload)
        for descriptor in ("05 01 09 06 A1 01 C0", "06 00", "06 00 FF 09 01"):
            with self.assertRaisesRegex(ValueError, "Unrecognized"):
                hid.reboot_payload(bytes.fromhex(descriptor))

    def test_discovery_filters_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nodes = root / "class"
            dev = root / "dev"
            nodes.mkdir()
            dev.mkdir()

            def add(number, pid, interface_class="03", out_size="0040"):
                interface = root / f"interface-{number}"
                device = interface / "hid"
                device.mkdir(parents=True)
                (interface / "bInterfaceNumber").write_text("01")
                (interface / "bInterfaceClass").write_text(interface_class)
                (device / "uevent").write_text(f"HID_ID=0003:00003233:{pid:08x}\n")
                for address, size in (("81", "0040"), ("02", out_size)):
                    endpoint = interface / f"ep_{address}"
                    endpoint.mkdir()
                    (endpoint / "bEndpointAddress").write_text(address)
                    (endpoint / "bmAttributes").write_text("03")
                    (endpoint / "wMaxPacketSize").write_text(size)
                raw = nodes / f"hidraw{number}"
                raw.mkdir()
                (raw / "device").symlink_to(device)
                path = dev / raw.name
                path.touch()
                return str(path)

            add(1, hid.APROM_PID, out_size="0008")
            add(2, hid.APROM_PID, interface_class="ff")
            add(3, hid.LDROM_PID)
            self.assertIsNone(hid.find_device(hid.APROM_PID, nodes, dev))
            expected = add(4, hid.APROM_PID)
            self.assertEqual(hid.find_device(hid.APROM_PID, nodes, dev), expected)
            add(5, hid.APROM_PID)
            with self.assertRaisesRegex(RuntimeError, "Multiple matching"):
                hid.find_device(hid.APROM_PID, nodes, dev)

    def test_programming_packet_layout(self):
        for size, count in ((3, 1), (42942, 767), (43084, 770)):
            with self.subTest(size=size):
                image = (bytes(range(256)) * (size // 256 + 1))[:size]
                packets = recovery.build_packets(image)
                self.assertEqual(len(packets), count)
                self.assertTrue(all(len(packet) == 64 for packet in packets))
                self.assertEqual(packets[0][:12], b"\xA0" + bytes(11))
                self.assertEqual(struct.unpack_from("<I", packets[0], 12), (size,))
                self.assertTrue(all(packet[:8] == bytes(8) for packet in packets[1:]))
                data = packets[0][16:] + b"".join(packet[8:] for packet in packets[1:])
                self.assertEqual(data[:size], image)
                self.assertEqual(data[size:], bytes(len(data) - size))


class CompatibilityTests(unittest.TestCase):
    def test_image_validation_and_build_hash_agree(self):
        self.assertEqual(build_patch.SUPPORTED_FIRMWARE["1.16"]["sha256"], recovery.STOCK.sha256)
        image = b"fixture"
        digest = hashlib.sha256(image).hexdigest()
        profile = replace(recovery.STOCK, size=len(image), sha256=digest)
        self.assertEqual(recovery.verify_image(image, profile), digest)
        with self.assertRaises(ValueError):
            recovery.verify_image(b"modifie", profile)
        with self.assertRaises(ValueError):
            recovery.verify_image(image, replace(profile, size=len(image) + 1))
        with self.assertRaises(ValueError):
            build_patch.verify_firmware(image)

    def test_cli_rejects_conflicts_and_unconfirmed_flash(self):
        bad = (
            [], ["--detect", "--inspect"], ["--detect", "image.bin"],
            ["--enter-bootloader", "--bootloader-only"],
            ["--stay-in-bootloader"], ["image.bin", "--bootloader-only"],
            ["image.bin", "--flash"], ["image.bin", "--confirm", "RESTORE-DUCKY-1.16"],
            ["image.bin", "--flash", "--confirm", "FLASH-DUCKY-V3"],
        )
        for argv in bad:
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    recovery.parse_args(argv, recovery.STOCK)
                self.assertEqual(error.exception.code, 2)
        inspected = recovery.parse_args(
            ["--inspect", "--stay-in-bootloader", "--bootloader-only"], recovery.STOCK
        )
        self.assertTrue(inspected.inspect and inspected.stay_in_bootloader and inspected.bootloader_only)
        flashed = recovery.parse_args(
            ["image.bin", "--flash", "--confirm", "FLASH-DUCKY-V3"], recovery.V3
        )
        self.assertTrue(flashed.flash)

    def test_dry_run_never_accesses_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "firmware.bin"
            path.write_bytes(b"fixture")
            profile = replace(recovery.STOCK, size=7, sha256=hashlib.sha256(b"fixture").hexdigest())
            with patch.object(recovery, "run_device_operation") as operation:
                with contextlib.redirect_stdout(io.StringIO()):
                    recovery.main([str(path)], profile)
            operation.assert_not_called()

    def test_inspect_accepts_unknown_config_and_returns_to_aprom(self):
        args = recovery.parse_args(["--inspect"], recovery.STOCK)
        self.run_with_mock_device(args, (0x33, 0x01205212, 0xF7FFFF7C, 0x32800))

    def test_unknown_config_rejects_programming(self):
        args = recovery.parse_args(
            ["image.bin", "--flash", "--confirm", recovery.STOCK.confirmation], recovery.STOCK
        )
        with self.assertRaisesRegex(RuntimeError, "Before programming.*No programming commands"):
            self.run_with_mock_device(
                args, (0x33, 0x01205212, 0xF7FFFF7C, 0x32800), expect_boot=False
            )

    def test_programming_ack_failure_keeps_ldrom(self):
        args = recovery.parse_args(
            ["image.bin", "--flash", "--confirm", recovery.STOCK.confirmation], recovery.STOCK
        )
        with self.assertRaisesRegex(RuntimeError, "Programming started.*Flash may be incomplete"):
            self.run_with_mock_device(args, recovery.STOCK.identity, expect_boot=False,
                                      reply_error=TimeoutError("no acknowledgment"))

    def test_failure_before_first_write_does_not_report_corruption(self):
        args = recovery.parse_args(
            ["image.bin", "--flash", "--confirm", recovery.STOCK.confirmation], recovery.STOCK
        )
        with self.assertRaisesRegex(RuntimeError, "Before programming.*No programming commands"):
            self.run_with_mock_device(args, recovery.STOCK.identity, expect_boot=False,
                                      write_error=OSError("write failed"))

    def run_with_mock_device(self, args, identity, expect_boot=True, reply_error=None, write_error=None):
        transport = SimpleNamespace(
            APROM_PID=hid.APROM_PID, LDROM_PID=hid.LDROM_PID, ShortHIDWrite=hid.ShortHIDWrite
        )
        with (
            patch.object(recovery, "hid", transport),
            patch.object(recovery, "open_ldrom", return_value=("/dev/mock-boot", 11)),
            patch.object(recovery.os, "close") as close,
            patch.object(transport, "inspect_ldrom", return_value=identity, create=True),
            patch.object(transport, "sync", create=True),
            patch.object(transport, "write_report", side_effect=write_error, create=True),
            patch.object(transport, "read_reply", side_effect=reply_error, create=True),
            patch.object(transport, "send", create=True) as send,
            patch.object(transport, "wait_device", return_value=("/dev/mock-app", 12), create=True),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            try:
                recovery.run_device_operation(args, recovery.STOCK, [bytes(64)])
            finally:
                if expect_boot:
                    send.assert_called_once_with(11, 0xAB, expect_reply=False)
                else:
                    send.assert_not_called()
                close.assert_any_call(11)


if __name__ == "__main__":
    unittest.main()
