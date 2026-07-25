#!/usr/bin/env bash
# Historical filename retained for compatibility. This script only stages files
# under this repository; it never installs into the running system.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DESTDIR="$REPO/stage/generic"
LIBDIR="usr/lib"
UDEVDIR="usr/lib/udev/rules.d"
ARTIFACT="$REPO/prebuilt/libfprint-2-tod-1-broadcom-5833.probe.so"

usage() {
    cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --destdir DIR       Repository-local package root (default: stage/generic)
  --libdir PATH       Relative library prefix (default: usr/lib)
  --udevdir PATH      Relative udev rules directory
  --artifact FILE     Repository-local patched plugin

Despite its historical name, this is a staging tool. It refuses destinations
outside ./stage and does not use sudo, reload udev, restart services, or alter
authentication.
EOF
}

while (($#)); do
    case "$1" in
        --destdir)
            DESTDIR="${2:?--destdir requires a value}"
            shift 2
            ;;
        --libdir)
            LIBDIR="${2:?--libdir requires a value}"
            shift 2
            ;;
        --udevdir)
            UDEVDIR="${2:?--udevdir requires a value}"
            shift 2
            ;;
        --artifact)
            ARTIFACT="${2:?--artifact requires a value}"
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

for relative_path in "$LIBDIR" "$UDEVDIR"; do
    if [[ "$relative_path" == /* ||
          "$relative_path" == ".." ||
          "$relative_path" == ../* ||
          "$relative_path" == */../* ||
          "$relative_path" == */.. ]]; then
        echo "library and udev paths must be safe relative paths: $relative_path" >&2
        exit 2
    fi
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

if [[ "$DESTDIR" != /* ]]; then
    DESTDIR="$REPO/$DESTDIR"
fi
mkdir -p "$DESTDIR"
DESTDIR="$(realpath "$DESTDIR")"
if [[ "$DESTDIR" != "$REPO"/stage && "$DESTDIR" != "$REPO"/stage/* ]]; then
    echo "refusing destination outside $REPO/stage: $DESTDIR" >&2
    exit 2
fi

PLUGIN_DIR="$DESTDIR/$LIBDIR/libfprint-2/tod-1"
RULE_DIR="$DESTDIR/$UDEVDIR"
mkdir -p "$PLUGIN_DIR" "$RULE_DIR"
install -m 0644 "$ARTIFACT" \
    "$PLUGIN_DIR/libfprint-2-tod-1-broadcom.so"
install -m 0644 "$REPO/udev/60-libfprint-2-tod1-broadcom-cv2.rules" \
    "$RULE_DIR/60-libfprint-2-tod1-broadcom-cv2.rules"

echo "Files staged under: $DESTDIR"
find "$DESTDIR" -type f -printf '%P\n' | sort
