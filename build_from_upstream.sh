#!/usr/bin/env bash
# Reproducible build: fetch the STOCK proprietary driver from Canonical's OEM
# repo and apply the CV2 patches locally. This avoids relying on the prebuilt
# binary in this repo (and is the recommended path for a clean GitHub fork).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
UPSTREAM="https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom"

echo "[*] Cloning upstream (branch: upstream) ..."
git clone --depth 1 -b upstream "$UPSTREAM" "$WORK/up"

STOCK="$WORK/up/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so"
[[ -f "$STOCK" ]] || { echo "stock .so not found in upstream tree" >&2; exit 1; }

echo "[*] Applying CV2 patches ..."
mkdir -p "$HERE/prebuilt"
python3 "$HERE/patch_driver.py" "$STOCK" "$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

echo "[*] Copying firmware blobs from upstream ..."
mkdir -p "$HERE/firmware"
cp -n "$WORK"/up/var/lib/fprint/fw/* "$HERE/firmware/" 2>/dev/null || true

rm -rf "$WORK"
echo "[*] Done. Now run:  ./install.sh"
