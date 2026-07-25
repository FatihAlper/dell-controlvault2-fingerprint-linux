#!/usr/bin/env bash
# Create an Arch-style package root inside the repository. This script never
# writes to /usr, /etc, /lib, invokes pacman, or reloads udev.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ARTIFACT="$REPO/prebuilt/libfprint-2-tod-1-broadcom-5833.probe.so"
STAGE="$REPO/stage/arch"

usage() {
    cat <<'EOF'
Usage: packaging/arch/stage.sh [--artifact FILE] [--stage-dir DIRECTORY]

Both the artifact and staging directory must resolve inside this repository.
The default staging root is ./stage/arch.
EOF
}

while (($#)); do
    case "$1" in
        --artifact)
            ARTIFACT="${2:?--artifact requires a value}"
            shift 2
            ;;
        --stage-dir)
            STAGE="${2:?--stage-dir requires a value}"
            shift 2
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

if [[ "$ARTIFACT" != /* ]]; then
    ARTIFACT="$REPO/$ARTIFACT"
fi
if [[ ! -f "$ARTIFACT" ]]; then
    echo "artifact not found: $ARTIFACT" >&2
    exit 1
fi
ARTIFACT="$(realpath "$ARTIFACT")"
if [[ "$ARTIFACT" != "$REPO"/* ]]; then
    echo "refusing artifact outside repository: $ARTIFACT" >&2
    exit 2
fi

if [[ "$STAGE" != /* ]]; then
    STAGE="$REPO/$STAGE"
fi
mkdir -p "$STAGE"
STAGE="$(realpath "$STAGE")"
if [[ "$STAGE" != "$REPO"/stage && "$STAGE" != "$REPO"/stage/* ]]; then
    echo "refusing staging directory outside $REPO/stage: $STAGE" >&2
    exit 2
fi

if ! file "$ARTIFACT" | grep -q 'ELF 64-bit.*shared object'; then
    echo "artifact is not an x86-64 ELF shared object: $ARTIFACT" >&2
    exit 1
fi
if ! readelf -d "$ARTIFACT" | grep -q 'libfprint-2-tod.so.1'; then
    echo "artifact does not require the expected TOD ABI" >&2
    exit 1
fi

PLUGIN_DIR="$STAGE/usr/lib/libfprint-2/tod-1"
UDEV_DIR="$STAGE/usr/lib/udev/rules.d"
mkdir -p "$PLUGIN_DIR" "$UDEV_DIR"
install -m 0644 "$ARTIFACT" \
    "$PLUGIN_DIR/libfprint-2-tod-1-broadcom.so"
install -m 0644 "$REPO/udev/60-libfprint-2-tod1-broadcom-cv2.rules" \
    "$UDEV_DIR/60-libfprint-2-tod1-broadcom-cv2.rules"

echo "Arch package root staged inside repository: $STAGE"
find "$STAGE" -type f -printf '%P\n' | sort
