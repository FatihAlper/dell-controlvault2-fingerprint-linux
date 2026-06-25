#!/usr/bin/env bash
# Install the patched ControlVault2 fingerprint driver (prebuilt) and its assets.
# Run from the repository root:  sudo ./install.sh   (or ./install.sh, it will sudo)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOD_DIR=/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1
FW_DIR=/var/lib/fprint/fw
SO="$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

if [[ ! -f "$SO" ]]; then
  echo "Prebuilt driver not found. Build it first:  ./build_from_upstream.sh" >&2
  exit 1
fi

SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"

echo "[*] Installing driver -> $TOD_DIR"
$SUDO mkdir -p "$TOD_DIR" "$FW_DIR"
$SUDO install -m644 "$SO" "$TOD_DIR/libfprint-2-tod-1-broadcom.so"

echo "[*] Installing firmware blobs -> $FW_DIR"
$SUDO cp -n "$HERE"/firmware/* "$FW_DIR"/ 2>/dev/null || true

echo "[*] Installing udev rule"
$SUDO install -m644 "$HERE/udev/61-broadcom-cv2-5834.rules" /lib/udev/rules.d/61-broadcom-cv2-5834.rules
$SUDO udevadm control --reload-rules
$SUDO udevadm trigger

echo "[*] Restarting fprintd"
$SUDO systemctl restart fprintd || true

echo
echo "Done. Next:"
echo "  fprintd-enroll        # enroll your finger (press, lift, repeat)"
echo "  fprintd-verify        # test recognition"
echo "  sudo pam-auth-update  # (optional) enable fingerprint login / sudo"
