# Dell ControlVault 2 fingerprint on Linux (Broadcom BCM5880, `0a5c:5834`)

Make the **Dell ControlVault 2 / Broadcom BCM5880 "USH"** fingerprint reader
(USB ID **`0a5c:5834`**) work under Linux with `fprintd` / `libfprint`.

This reader is found on many **Dell Latitude** laptops (7390, 7480, **7490**,
E7470, 5290, 5490, 5590, …). It has been considered *unsupported on Linux for
about a decade* — `libfprint` does not recognise it, and Dell only ships a closed
driver for the newer ControlVault **3** sensors.

This repo patches that closed driver so it also drives the older CV2 chip.

> ⚠️ **Unofficial.** Not affiliated with or endorsed by Dell, Broadcom or
> Canonical. It patches a **proprietary** binary. Use it on hardware you own.

---

## Is this for me?
Run `lsusb`. If you see:

```
Bus 00x Device 00x: ID 0a5c:5834 Broadcom Corp. 5880
```

…and `fprintd-enroll` says *"No devices available"*, this is for you.

---

## Quick start (prebuilt)

```bash
git clone <this-repo>
cd dell-controlvault2-fingerprint-linux
./install.sh                 # installs the patched driver + udev rule + firmware
fprintd-enroll               # enroll a finger (press, lift, repeat ~4-8x)
fprintd-verify               # test recognition
sudo pam-auth-update         # (optional) enable fingerprint login & sudo
```

If an OS / `libfprint` update ever wipes it, just run `./install.sh` again.

## Build from upstream (recommended for forks)

Instead of trusting the prebuilt binary, fetch Dell/Canonical's stock driver and
patch it yourself (needs `git`, `python3`):

```bash
./build_from_upstream.sh     # clones the OEM repo, applies patches into prebuilt/
./install.sh
```

---

## Status

| Capability | State |
|---|---|
| Device detected by `libfprint`/`fprintd` | ✅ works |
| Open / power-on | ✅ works |
| Fingerprint **capture** (sensor lights, grabs images) | ✅ works |
| **Enroll** → `enroll-completed` (template committed on-chip) | ✅ works |
| **Verify / match** (match-on-chip) | ✅ implemented (patches 4–5) — **please confirm on your unit** |

The hard part is **match-on-chip**: the template lives in the chip's secure
storage. Patches **4–5** route CV2's enrollment/verify status codes so the
template actually commits and the match result is reported. This is the newest
piece — if `fprintd-verify` gives `no-match`/`unknown-error` on your laptop,
please open an issue with a debug log (below); CV2 units may use slightly
different status codes that are trivial to add.

> Tip while enrolling: **lift your finger completely between presses** and shift
> its position a little each time. Failed grabs are ignored and harmless.

---

## Troubleshooting

**Enable debug logging** (to read what the chip returns):
```bash
sudo mkdir -p /etc/systemd/system/fprintd.service.d
printf '[Service]\nEnvironment=G_MESSAGES_DEBUG=all\nEnvironment=LIBFPRINT_DEBUG=3\n' \
  | sudo tee /etc/systemd/system/fprintd.service.d/debug.conf
sudo systemctl daemon-reload && sudo systemctl restart fprintd
# reproduce, then:
sudo journalctl -u fprintd --since "2 min ago" -o cat
```

- `Device status = (NN)` (decimal) during enroll, or `identify failed 0xNN`
  during verify → that `NN` is the CV status to map. See `PATCHES.md` #4/#5.
- Re-list / clear prints: `fprintd-list "$USER"`, `fprintd-delete "$USER"`.

---

## How it works
Five byte-level patches turn the CV3 driver into a CV2 driver. Full
reverse-engineering write-up and the exact signatures are in
**[PATCHES.md](PATCHES.md)**. The patcher (`patch_driver.py`) applies them by
unique byte signature, so it survives minor upstream binary changes, and it
reproduces the working driver **byte-for-byte**.

## Repo layout
```
install.sh              install the prebuilt driver + assets
build_from_upstream.sh  fetch stock driver from Launchpad and patch it
patch_driver.py         the 5 byte-patches (signature based)
uninstall.sh            remove it
prebuilt/               the patched .so (derived from Dell/Canonical's binary)
firmware/               CV firmware blobs (from upstream; not flashed on CV2)
udev/                   rule binding 0a5c:5834 to the driver
PATCHES.md              reverse-engineering notes
```

## Legal / license
The driver and firmware are **proprietary Dell/Canonical/Broadcom** artifacts,
redistributed here only as a convenience for owners of the hardware. There is no
open license on those binaries. If you publish a fork, prefer shipping **only**
the patcher + `build_from_upstream.sh` and letting users pull the stock binary
from Canonical's OEM repo themselves. The patches, scripts and docs in this repo
are released under the MIT license.

## Credits
Reverse-engineered from the shipped `.so` with `radare2` + `pyusb` on a Dell
Latitude 7490. USB transport groundwork inspired by the NFC work in
[`jacekkow/controlvault2-nfc-enable`](https://github.com/jacekkow/controlvault2-nfc-enable).
