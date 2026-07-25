#!/usr/bin/env bash
# Fetch or reuse Canonical's stock Broadcom TOD driver and patch it locally.
# All temporary and output files stay inside this repository.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM="https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom"
UPSTREAM_COMMIT="f7d31fcb9f6952d7d76ba50287e000c29760589d"
STOCK_SHA256="54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172"
SOURCE=""
TARGET_PID="5834"
PATCH_SET="full"
OUTPUT=""
COPY_FIRMWARE=0
WORK=""

usage() {
    cat <<'EOF'
Usage: ./build_from_upstream.sh [options]

Options:
  --target-pid PID       Target CV2 PID: 5833 or 5834 (default: 5834)
  --patch-set SET        probe or full (default: full)
  --source PATH          Existing stock .so or extracted source tree
  --output PATH          Output .so path (must remain inside the repository)
  --copy-firmware        Copy discovered firmware blobs into ./firmware
  -h, --help             Show this help

Without --source, the Canonical upstream branch is cloned into a temporary
directory under this repository. Nothing is installed into the system.
EOF
}

while (($#)); do
    case "$1" in
        --target-pid)
            TARGET_PID="${2:?--target-pid requires a value}"
            shift 2
            ;;
        --patch-set)
            PATCH_SET="${2:?--patch-set requires a value}"
            shift 2
            ;;
        --source)
            SOURCE="${2:?--source requires a path}"
            shift 2
            ;;
        --output)
            OUTPUT="${2:?--output requires a path}"
            shift 2
            ;;
        --copy-firmware)
            COPY_FIRMWARE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "$TARGET_PID" in
    5833|5834) ;;
    *)
        echo "unsupported target PID: $TARGET_PID (expected 5833 or 5834)" >&2
        exit 2
        ;;
esac

case "$PATCH_SET" in
    probe|full) ;;
    *)
        echo "unsupported patch set: $PATCH_SET (expected probe or full)" >&2
        exit 2
        ;;
esac

if [[ "$TARGET_PID" == 5833 && "$PATCH_SET" != probe ]]; then
    echo "0a5c:5833 is validated only with --patch-set probe" >&2
    echo "legacy enrollment/verify patches are intentionally disabled" >&2
    exit 2
fi

cleanup() {
    if [[ -n "$WORK" && -d "$WORK" && "$WORK" == "$HERE"/.build.* ]]; then
        rm -rf -- "$WORK"
    fi
}
trap cleanup EXIT

if [[ -z "$SOURCE" ]]; then
    WORK="$(mktemp -d "$HERE/.build.XXXXXX")"
    SOURCE="$WORK/upstream"
    echo "[*] Cloning Canonical upstream branch into repository-local workspace ..."
    git clone --depth 1 -b upstream "$UPSTREAM" "$SOURCE"
    ACTUAL_COMMIT="$(git -C "$SOURCE" rev-parse HEAD)"
    if [[ "$ACTUAL_COMMIT" != "$UPSTREAM_COMMIT" ]]; then
        echo "upstream branch changed: expected $UPSTREAM_COMMIT, got $ACTUAL_COMMIT" >&2
        echo "review the new binary before updating the pinned commit and checksum" >&2
        exit 1
    fi
fi

if [[ -f "$SOURCE" ]]; then
    STOCK="$SOURCE"
    SOURCE_ROOT="$(dirname "$SOURCE")"
elif [[ -d "$SOURCE" ]]; then
    SOURCE_ROOT="$SOURCE"
    mapfile -d '' STOCK_CANDIDATES < <(
        find "$SOURCE_ROOT" -type f \
            -name 'libfprint-2-tod-1-broadcom.so' -print0
    )
    if ((${#STOCK_CANDIDATES[@]} != 1)); then
        echo "expected exactly one stock Broadcom TOD .so under $SOURCE_ROOT; found ${#STOCK_CANDIDATES[@]}" >&2
        exit 1
    fi
    STOCK="${STOCK_CANDIDATES[0]}"
else
    echo "source does not exist: $SOURCE" >&2
    exit 1
fi

ACTUAL_STOCK_SHA256="$(sha256sum "$STOCK" | cut -d' ' -f1)"
if [[ "$ACTUAL_STOCK_SHA256" != "$STOCK_SHA256" ]]; then
    echo "stock driver checksum mismatch" >&2
    echo "expected: $STOCK_SHA256" >&2
    echo "actual:   $ACTUAL_STOCK_SHA256" >&2
    exit 1
fi

if [[ -z "$OUTPUT" ]]; then
    OUTPUT="$HERE/prebuilt/libfprint-2-tod-1-broadcom-${TARGET_PID}.${PATCH_SET}.so"
elif [[ "$OUTPUT" != /* ]]; then
    OUTPUT="$HERE/$OUTPUT"
fi

OUTPUT_PARENT="$(dirname "$OUTPUT")"
mkdir -p "$OUTPUT_PARENT"
OUTPUT_PARENT_REAL="$(realpath "$OUTPUT_PARENT")"
if [[ "$OUTPUT_PARENT_REAL" != "$HERE" && "$OUTPUT_PARENT_REAL" != "$HERE"/* ]]; then
    echo "refusing output outside repository: $OUTPUT" >&2
    exit 2
fi
OUTPUT="$OUTPUT_PARENT_REAL/$(basename "$OUTPUT")"

echo "[*] Stock driver: $STOCK"
echo "[*] Stock SHA-256 verified: $STOCK_SHA256"
echo "[*] Applying $PATCH_SET patch set for 0a5c:$TARGET_PID ..."
python3 "$HERE/patch_driver.py" \
    --target-pid "$TARGET_PID" \
    --patch-set "$PATCH_SET" \
    "$STOCK" "$OUTPUT"

if ((COPY_FIRMWARE)); then
    mapfile -d '' FW_CANDIDATES < <(
        find "$SOURCE_ROOT" -type f -path '*/fprint/fw/*' -print0
    )
    if ((${#FW_CANDIDATES[@]} == 0)); then
        echo "no firmware blobs found under $SOURCE_ROOT" >&2
        exit 1
    fi
    mkdir -p "$HERE/firmware"
    cp -n -- "${FW_CANDIDATES[@]}" "$HERE/firmware/"
    echo "[*] Copied ${#FW_CANDIDATES[@]} firmware file(s) into $HERE/firmware"
fi

echo "[*] Repository-local build complete: $OUTPUT"
