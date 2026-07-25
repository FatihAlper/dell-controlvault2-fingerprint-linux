import importlib.util
import struct
import unittest
from pathlib import Path


PROBE_PATH = Path(__file__).parents[1] / "docs" / "cv_usb_probe.py"
SPEC = importlib.util.spec_from_file_location("cv_usb_probe", PROBE_PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class FakeEndpoint:
    def __init__(self, address):
        self.bEndpointAddress = address


class FakeInterface:
    def __init__(self, *addresses):
        self.endpoints = [FakeEndpoint(address) for address in addresses]

    def __iter__(self):
        return iter(self.endpoints)


class ProbeTests(unittest.TestCase):
    def test_parse_usb_id(self):
        self.assertEqual(probe.parse_usb_id("5833"), 0x5833)
        self.assertEqual(probe.parse_usb_id("0A5C"), 0x0A5C)

    def test_encap_get_version_header(self):
        packet = probe.encap(0x39)
        self.assertEqual(len(packet), 44)
        self.assertEqual(struct.unpack_from("<I", packet, 0x00)[0], 1)
        self.assertEqual(struct.unpack_from("<I", packet, 0x04)[0], 44)
        self.assertEqual(struct.unpack_from("<H", packet, 0x08)[0], 0x39)
        self.assertEqual(struct.unpack_from("<H", packet, 0x0A)[0], 0x40)
        self.assertEqual(struct.unpack_from("<I", packet, 0x28)[0], 0)

    def test_expected_transport_accepts_extra_endpoints(self):
        interface = FakeInterface(0x01, 0x81, 0x85, 0x87)
        self.assertTrue(
            probe.EXPECTED_ENDPOINTS.issubset(probe.endpoint_addresses(interface))
        )

    def test_expected_transport_rejects_missing_interrupt_endpoint(self):
        interface = FakeInterface(0x01, 0x81)
        self.assertFalse(
            probe.EXPECTED_ENDPOINTS.issubset(probe.endpoint_addresses(interface))
        )

    def test_stateful_command_requires_explicit_acknowledgement(self):
        parser = probe.build_parser()
        args = parser.parse_args(
            ["--pid", "5833", "--stage", "command", "--command", "init"]
        )
        self.assertEqual(args.pid, 0x5833)
        with self.assertRaisesRegex(SystemExit, "may change device state"):
            probe.validate_args(args)

    def test_stateful_command_can_be_explicitly_acknowledged(self):
        parser = probe.build_parser()
        args = parser.parse_args(
            [
                "--pid",
                "5833",
                "--stage",
                "command",
                "--command",
                "init",
                "--allow-stateful-command",
            ]
        )
        probe.validate_args(args)

    def test_get_version_is_allowed_without_stateful_acknowledgement(self):
        parser = probe.build_parser()
        args = parser.parse_args(
            ["--pid", "5833", "--stage", "command", "--command", "get-version"]
        )
        probe.validate_args(args)


if __name__ == "__main__":
    unittest.main()
