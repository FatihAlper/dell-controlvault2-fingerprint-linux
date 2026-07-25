#!/usr/bin/env python3
"""Staged ControlVault 2 USB probe.

The default ``enumerate`` stage is transfer-free.  A caller must explicitly
select ``open`` to claim interface 0, or ``command`` to send exactly one
allow-listed bring-up command.
"""

from __future__ import annotations

import argparse
import logging
import struct
import sys
from collections.abc import Iterable

VID_DEFAULT = 0x0A5C
PID_DEFAULT = 0x5834
INTERFACE = 0
EP_OUT = 0x01
EP_BULK_IN = 0x81
EP_INTR_IN = 0x85
EXPECTED_ENDPOINTS = {EP_OUT, EP_BULK_IN, EP_INTR_IN}

# Commands recovered from the proprietary driver's dynamic symbols.  Only the
# version query is classified as read-only enough for the first hardware test.
COMMANDS = {
    "get-version": (0x39, "cv_get_ush_ver"),
    "open": (0x02, "cv_open"),
    "init": (0x06, "cv_init"),
    "detect-finger": (0x80, "cv_detect_fp"),
    "enable": (0x3F, "cv_enable"),
    "enable-fingerprint": (0x41, "cv_enable_fingerprint"),
}
SAFE_COMMANDS = {"get-version"}

log = logging.getLogger("cv")


def parse_usb_id(value: str) -> int:
    """Parse a four-digit hexadecimal USB vendor/product ID."""
    try:
        parsed = int(value, 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid hexadecimal USB ID: {value}") from error
    if not 0 <= parsed <= 0xFFFF:
        raise argparse.ArgumentTypeError(f"USB ID out of range: {value}")
    return parsed


def hex_bytes(data: Iterable[int]) -> str:
    return " ".join(f"{byte:02x}" for byte in bytes(data))


def ascii_bytes(data: Iterable[int]) -> str:
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in bytes(data))


def encap(cmd_id: int, params: bytes = b"", flags: int = 0x0040, libver: int = 0) -> bytes:
    """Build the raw 44-byte CV command header used on interface 0."""
    header = bytearray(0x2C)
    struct.pack_into("<I", header, 0x00, 1)
    struct.pack_into("<I", header, 0x04, 0x2C + len(params))
    struct.pack_into("<H", header, 0x08, cmd_id)
    struct.pack_into("<H", header, 0x0A, flags)
    struct.pack_into("<I", header, 0x0C, libver)
    struct.pack_into("<I", header, 0x28, len(params))
    return bytes(header) + params


def endpoint_addresses(interface) -> set[int]:
    return {endpoint.bEndpointAddress for endpoint in interface}


def validate_transport(device) -> tuple[bool, set[int]]:
    """Check interface 0 and return whether its endpoint set matches CV2."""
    interface = device.get_active_configuration()[(INTERFACE, 0)]
    endpoints = endpoint_addresses(interface)
    return EXPECTED_ENDPOINTS.issubset(endpoints), endpoints


def claim_interface(device, usb_util) -> bool:
    """Claim interface 0 and return whether a kernel driver was detached."""
    detached = False
    try:
        if device.is_kernel_driver_active(INTERFACE):
            device.detach_kernel_driver(INTERFACE)
            detached = True
    except (NotImplementedError, AttributeError):
        pass
    usb_util.claim_interface(device, INTERFACE)
    return detached


def release_interface(device, usb_util, detached: bool) -> None:
    usb_util.release_interface(device, INTERFACE)
    if detached:
        try:
            device.attach_kernel_driver(INTERFACE)
        except (NotImplementedError, AttributeError):
            log.warning("[!] could not reattach the previous kernel driver")
    usb_util.dispose_resources(device)


def read_endpoint(device, endpoint: int, size: int, timeout_ms: int, usb_error):
    try:
        return device.read(endpoint, size, timeout=timeout_ms).tobytes(), None
    except usb_error as error:
        return None, error


def run_command(
    device,
    command_name: str,
    timeout_ms: int,
    usb_error,
    *,
    show_payload: bool = False,
) -> bool:
    command_id, symbol = COMMANDS[command_name]
    packet = encap(command_id)
    log.info("=== %s (0x%02x) ===", symbol, command_id)
    log.info("[>] OUT 0x01 request length=%d", len(packet))
    if show_payload:
        log.info("[>] OUT 0x01 payload: %s", hex_bytes(packet))
    written = device.write(EP_OUT, packet, timeout=timeout_ms)
    if written != len(packet):
        raise RuntimeError(f"short USB write: {written}/{len(packet)} bytes")
    log.info("    wrote %d bytes", written)

    interrupt, interrupt_error = read_endpoint(
        device, EP_INTR_IN, 32, timeout_ms, usb_error
    )
    if interrupt is not None:
        log.info("[<] INTR 0x85 response length=%d", len(interrupt))
        if show_payload:
            log.info(
                "[<] INTR 0x85 payload: %s | %s",
                hex_bytes(interrupt),
                ascii_bytes(interrupt),
            )
    else:
        log.info("[<] INTR 0x85: no reply (%s)", interrupt_error)

    bulk, bulk_error = read_endpoint(device, EP_BULK_IN, 256, timeout_ms, usb_error)
    if bulk is not None:
        log.info("[<] BULK 0x81 response length=%d", len(bulk))
        if show_payload:
            log.info(
                "[<] BULK 0x81 payload: %s | %s",
                hex_bytes(bulk),
                ascii_bytes(bulk),
            )
    else:
        log.info("[<] BULK 0x81: no reply (%s)", bulk_error)

    return interrupt is not None or bulk is not None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vid", type=parse_usb_id, default=VID_DEFAULT)
    parser.add_argument("--pid", type=parse_usb_id, default=PID_DEFAULT)
    parser.add_argument(
        "--stage",
        choices=("enumerate", "open", "command"),
        default="enumerate",
        help="enumerate performs no transfers; open only claims/releases interface 0",
    )
    parser.add_argument("--command", choices=COMMANDS, default="get-version")
    parser.add_argument(
        "--allow-stateful-command",
        action="store_true",
        help="permit a command other than the read-only get-version query",
    )
    parser.add_argument(
        "--show-payload",
        action="store_true",
        help=(
            "print request/response bytes; never publish logs containing "
            "device payloads"
        ),
    )
    parser.add_argument("--timeout-ms", type=int, default=3000)
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    if (
        args.stage == "command"
        and args.command not in SAFE_COMMANDS
        and not args.allow_stateful_command
    ):
        raise SystemExit(
            f"{args.command!r} may change device state; "
            "pass --allow-stateful-command to acknowledge"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_args(args)

    try:
        import usb.core
        import usb.util
    except ModuleNotFoundError:
        log.error("PyUSB is required; install requirements-probe.txt in a local venv")
        return 10

    device = usb.core.find(idVendor=args.vid, idProduct=args.pid)
    if device is None:
        log.error("[!] device %04x:%04x not found", args.vid, args.pid)
        return 2

    log.info("[+] found %04x:%04x", args.vid, args.pid)
    try:
        matches, endpoints = validate_transport(device)
    except (KeyError, usb.core.USBError) as error:
        log.error("[!] could not inspect interface 0: %s", error)
        return 3

    log.info(
        "[+] interface 0 endpoints: %s",
        ", ".join(f"0x{endpoint:02x}" for endpoint in sorted(endpoints)),
    )
    if not matches:
        log.error(
            "[!] transport mismatch; required endpoints are %s",
            ", ".join(f"0x{endpoint:02x}" for endpoint in sorted(EXPECTED_ENDPOINTS)),
        )
        return 4
    log.info("[+] interface 0 matches the expected CV2 transport")

    if args.stage == "enumerate":
        log.info("[+] enumerate stage passed; no interface claimed and no transfer sent")
        return 0

    claimed = False
    detached = False
    try:
        detached = claim_interface(device, usb.util)
        claimed = True
        log.info("[+] interface 0 claimed")
        if args.stage == "open":
            log.info("[+] open stage passed; no transfer sent")
            return 0
        replied = run_command(
            device,
            args.command,
            args.timeout_ms,
            usb.core.USBError,
            show_payload=args.show_payload,
        )
        if not replied:
            log.error("[!] command completed without a reply")
            return 6
        log.info("[+] command stage passed with a device reply")
        return 0
    except usb.core.USBError as error:
        log.error("[!] USB operation failed: %s", error)
        return 5
    finally:
        if claimed:
            try:
                release_interface(device, usb.util, detached)
            except usb.core.USBError as error:
                log.warning("[!] interface cleanup failed: %s", error)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
