#!/usr/bin/env bash
# Remove files created by the repository-local staging tool only.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DESTDIR="$REPO/stage/generic"
LIBDIR="usr/lib"
UDEVDIR="usr/lib/udev/rules.d"

usage() {
    cat <<'EOF'
Usage: ./uninstall.sh [--destdir DIR] [--libdir PATH] [--udevdir PATH]

Only explicit generated files under this repository's ./stage directory are
removed. The running system is never changed.
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

if [[ "$DESTDIR" != /* ]]; then
    DESTDIR="$REPO/$DESTDIR"
fi
if [[ ! -d "$DESTDIR" ]]; then
    echo "staging directory does not exist: $DESTDIR"
    exit 0
fi
DESTDIR="$(realpath "$DESTDIR")"
if [[ "$DESTDIR" != "$REPO"/stage/* ]]; then
    echo "refusing destination outside $REPO/stage: $DESTDIR" >&2
    exit 2
fi

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

PLUGIN="$DESTDIR/$LIBDIR/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so"
RULE="$DESTDIR/$UDEVDIR/60-libfprint-2-tod1-broadcom-cv2.rules"
rm -f -- "$PLUGIN" "$RULE"
echo "Removed repository-local staged files:"
printf '%s\n%s\n' "$PLUGIN" "$RULE"
