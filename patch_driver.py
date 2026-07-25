#!/usr/bin/env python3
"""Patch Canonical's Broadcom TOD driver for a selected ControlVault 2 PID.

The ``probe`` patch set contains only the changes needed for device binding and
``dev_probe``.  The ``full`` patch set retains the project's existing
enrollment and verification patches for the original ``0a5c:5834`` target.
The ``0a5c:5833`` target is intentionally restricted to ``probe``.

Usage:
    python3 patch_driver.py --target-pid 5833 --patch-set probe INPUT OUTPUT

See PATCHES.md for the reverse-engineering rationale and source binary details.
"""

from __future__ import annotations

import argparse
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


CV3_SOURCE_PID = 0x5842
CV2_TARGET_PIDS = (0x5833, 0x5834)
VENDOR_ID = 0x0A5C


@dataclass(frozen=True)
class Patch:
    description: str
    find: bytes
    replace: bytes


class PatchError(RuntimeError):
    pass


def parse_target_pid(value: str) -> int:
    try:
        pid = int(value, 16)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid hexadecimal USB PID: {value}") from error
    if pid not in CV2_TARGET_PIDS:
        supported = ", ".join(f"{known:04x}" for known in CV2_TARGET_PIDS)
        raise argparse.ArgumentTypeError(
            f"unsupported target PID {pid:04x}; validated targets: {supported}"
        )
    return pid


def make_patches(target_pid: int, patch_set: str) -> tuple[Patch, ...]:
    if target_pid not in CV2_TARGET_PIDS:
        raise ValueError(f"unvalidated target PID: {target_pid:04x}")
    if patch_set not in {"probe", "full"}:
        raise ValueError(f"unknown patch set: {patch_set}")
    if target_pid == 0x5833 and patch_set != "probe":
        raise ValueError(
            "0a5c:5833 is validated only for the probe patch set; "
            "the legacy enrollment/verify patches are intentionally disabled"
        )

    probe_patches = (
        Patch(
            f"1. id_table: replace CV3 PID 0x{CV3_SOURCE_PID:04x} with "
            f"CV2 PID 0x{target_pid:04x}",
            struct.pack("<II", CV3_SOURCE_PID, VENDOR_ID),
            struct.pack("<II", target_pid, VENDOR_ID),
        ),
        Patch(
            "2. USB enumerator: bypass the CV3-only PID filter",
            bytes.fromhex("66f7c1fdff 740c"),
            bytes.fromhex("66f7c1fdff eb0c"),
        ),
        Patch(
            "3. dev_probe: treat chip-type error 0x1c as probe success",
            bytes.fromhex("83f81c 741f"),
            bytes.fromhex("83f81c 743a"),
        ),
    )
    if patch_set == "probe":
        return probe_patches

    return probe_patches + (
        Patch(
            "4. enroll: route CV2 status 0x59 to the template commit path",
            bytes.fromhex("4181fda4000000 0f84fd010000"),
            bytes.fromhex("4181fd59000000 0f84160000 00"),
        ),
        Patch(
            "5. verify: always call verify_report",
            bytes.fromhex("85d2 0f858a000000 83f801"),
            bytes.fromhex("85d2 909090909090 83f801"),
        ),
    )


def apply_patches(data: bytes, patches: Sequence[Patch]) -> bytes:
    patched = bytearray(data)
    for patch in patches:
        if len(patch.find) != len(patch.replace):
            raise PatchError(f"patch length mismatch: {patch.description}")
        matches = patched.count(patch.find)
        if matches == 0:
            raise PatchError(
                "signature not found for patch:\n"
                f"  {patch.description}\n"
                "  (is this the expected stock libfprint-2-tod-1-broadcom.so?)"
            )
        if matches > 1:
            raise PatchError(
                f"signature ambiguous ({matches} hits) for patch:\n"
                f"  {patch.description}"
            )
        offset = patched.index(patch.find)
        patched[offset : offset + len(patch.find)] = patch.replace
        print(f"[ok] {patch.description} @ file offset 0x{offset:x}")
    return bytes(patched)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="stock Broadcom TOD shared object")
    parser.add_argument("output", type=Path, help="patched output shared object")
    parser.add_argument(
        "--target-pid",
        type=parse_target_pid,
        default=0x5834,
        metavar="PID",
        help="CV2 USB PID in hexadecimal (default: 5834)",
    )
    parser.add_argument(
        "--patch-set",
        choices=("probe", "full"),
        default="full",
        help="probe applies patches 1-3 only; full also applies enroll/verify patches",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    patches = make_patches(args.target_pid, args.patch_set)
    try:
        patched = apply_patches(args.input.read_bytes(), patches)
    except (OSError, PatchError) as error:
        raise SystemExit(f"FAILED: {error}") from error

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(patched)
    except OSError as error:
        raise SystemExit(f"FAILED: could not write {args.output}: {error}") from error

    print(f"\nPatched driver written to: {args.output}")
    print(f"Target USB ID: {VENDOR_ID:04x}:{args.target_pid:04x}")
    print(f"Patch set: {args.patch_set} ({len(patches)} patches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
