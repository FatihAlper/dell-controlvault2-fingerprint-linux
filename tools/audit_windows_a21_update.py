#!/usr/bin/env python3
"""Validate static UpdateEnrollment anchors in Dell's Windows A21 binaries.

The tool is deliberately read-only.  It does not extract, execute, patch, or
copy either proprietary binary; callers must provide their own extracted
files from the supported Dell package.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path


class AuditError(RuntimeError):
    """An input is not the exact artifact covered by the static analysis."""


@dataclass(frozen=True)
class ArtifactProfile:
    name: str
    sha256: str
    signatures: dict[str, bytes]
    expected_offsets: dict[str, int]


ENGINE_PROFILE = ArtifactProfile(
    name="BrcmEngineAdapter.dll",
    sha256="622b1a12566cb313cde264869ca5a4b410e3d5b2b604f5dd628c4a6b709b19ae",
    signatures={
        # HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, 0x290)
        "zeroed_engine_context_allocation": bytes.fromhex(
            "ff158da50100ba0800000041b890020000488bc8ff1591a50100"
        ),
        # arg1=&EngineContext[0x18], arg3=&inner[0x2c], arg4=false,
        # arg2/arg5 are stack outputs, then call CSS_FingerprintUpdateEnrollment.
        "update_call_arguments": bytes.fromhex(
            "488d4424704533c9488d4f184889442420"
            "4c8d452c488d542460ff15f9f80200"
        ),
    },
    expected_offsets={
        "zeroed_engine_context_allocation": 0xF65,
        "update_call_arguments": 0x25A7,
    },
)


BIP_PROFILE = ArtifactProfile(
    name="bipdll.dll",
    sha256="30c556a9b542d0fcf29a6822b3bb81fe23ce2917b403b3f25af9384e0e31e524",
    signatures={
        # CSS_FingerprintUpdateEnrollment forwards handle, 20-byte input,
        # auxiliary size/pointer, and its three output pointers to 0x2d110.
        "wrapper_dispatch_arguments": bytes.fromhex(
            "488b4424584c8bcb8b4e20448bc54c89742430"
            "498bd448894424284c896c2420e872700100"
        ),
        # The generic dispatcher registers arg2 as a 0x14-byte input.
        "generic_input_20_bytes": bytes.fromhex(
            "4c8d4c24784d8bc6ba1400000033c9e8bcb40100"
        ),
        # A zero auxiliary length is represented by a null pointer and size.
        "generic_zero_auxiliary": bytes.fromhex(
            "4533c033d24c8d8c2480000000b902000000e84cb40100"
        ),
        # The generic path builds native command 0x6c.
        "generic_command_0x6c": bytes.fromhex(
            "b86c00000066894424384533e44489642430"
            "8b44245c894424284c89642420"
        ),
    },
    expected_offsets={
        "wrapper_dispatch_arguments": 0x15479,
        "generic_input_20_bytes": 0x2C730,
        "generic_zero_auxiliary": 0x2C79D,
        "generic_command_0x6c": 0x2C8A5,
    },
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_artifact(
    path: Path,
    profile: ArtifactProfile,
    *,
    expected_sha256: str | None = None,
) -> dict[str, int]:
    data = path.read_bytes()
    wanted_hash = expected_sha256 or profile.sha256
    actual_hash = sha256_bytes(data)
    if actual_hash != wanted_hash:
        raise AuditError(
            f"unsupported {profile.name} SHA-256: expected {wanted_hash}, "
            f"got {actual_hash}"
        )

    offsets: dict[str, int] = {}
    for name, signature in profile.signatures.items():
        count = data.count(signature)
        if count != 1:
            raise AuditError(
                f"{profile.name} signature {name!r} occurs {count} times; "
                "expected exactly once"
            )
        offset = data.index(signature)
        expected_offset = profile.expected_offsets[name]
        if offset != expected_offset:
            raise AuditError(
                f"{profile.name} signature {name!r} is at 0x{offset:x}; "
                f"expected 0x{expected_offset:x}"
            )
        offsets[name] = offset
    return offsets


def report(profile: ArtifactProfile, offsets: dict[str, int]) -> None:
    print(f"artifact.{profile.name}.sha256={profile.sha256}")
    for name, offset in offsets.items():
        print(f"artifact.{profile.name}.signature.{name}=0x{offset:x}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only validation of Windows A21 UpdateEnrollment instruction "
            "anchors. The supported files come from Dell package N23KC A21."
        )
    )
    parser.add_argument("engine_adapter", type=Path)
    parser.add_argument("bipdll", type=Path)
    args = parser.parse_args()

    try:
        engine_offsets = validate_artifact(args.engine_adapter, ENGINE_PROFILE)
        bip_offsets = validate_artifact(args.bipdll, BIP_PROFILE)
    except (OSError, AuditError) as error:
        parser.error(str(error))

    report(ENGINE_PROFILE, engine_offsets)
    report(BIP_PROFILE, bip_offsets)
    print("derived.engine_context_allocation=zeroed")
    print("derived.update_input=engine_context_plus_0x18_length_20")
    print("derived.update_auxiliary=false_size_0_pointer_null")
    print("derived.generic_command=0x6c")
    print("artifact_write_performed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
