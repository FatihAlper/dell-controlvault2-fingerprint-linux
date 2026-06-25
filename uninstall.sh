#!/usr/bin/env bash
# Remove the patched driver and assets. Your enrolled prints live on the chip;
# remove them first with: fprintd-delete "$USER"
set -euo pipefail
SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"
$SUDO rm -f /usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so
$SUDO rm -f /lib/udev/rules.d/61-broadcom-cv2-5834.rules
$SUDO udevadm control --reload-rules && $SUDO udevadm trigger
$SUDO systemctl restart fprintd || true
echo "Removed. (Firmware blobs in /var/lib/fprint/fw left in place; delete manually if desired.)"
