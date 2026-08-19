# Dell ControlVault 2 fingerprint on Linux

> **Archived:** Active ControlVault2 research and future driver work moved to
> [`FatihAlper/dell-controlvault2-research`](https://github.com/FatihAlper/dell-controlvault2-research).
> This fork is preserved read-only for historical links and provenance.

Bring-up tooling and byte patches for the proprietary Broadcom TOD driver used
with Dell ControlVault 2 / BCM5880 fingerprint devices:

- `0a5c:5834` — the project's original target
- `0a5c:5833` — probe support validated on a Dell Latitude 7390

This is unofficial and is not affiliated with Dell, Broadcom, or Canonical.
The stock driver is proprietary; generated binaries are intentionally ignored
by Git.

## Current 5833 status

The validated lifecycle is:

```text
enumeration -> plugin load -> probe -> open -> capture -> clean close
```

On the tested Latitude 7390:

| Check | Result |
|---|---|
| Interface 0 endpoints | `0x01` bulk OUT, `0x81` bulk IN, `0x85` interrupt IN |
| `cv_get_ush_ver` (`0x39`) | 44-byte write, interrupt reply, 44-byte bulk reply |
| TOD plugin load | `broadcom` / `Broadcom Sensors`, runtime table contains `0a5c:5833` |
| Driver probe | `cv_get_ush_ver() status: 0x0`; expected CV2 chip-type result `0x1c`; probe completion |
| Public open/close | Both complete successfully |
| Capture retry | `0x89 → 0x8a → new capture` works on hardware |
| Bounded `0x59` diagnostic | A single repeated update returns `0x89` and allows progress to continue |
| Enrollment completion | Incomplete; completion remains zero |
| Commit and verify | Not proven |

Capture and retry recovery work on the tested BCM5880 device, but enrollment
completion, template commit, and verification remain incomplete. The bounded
`0x59` retry is a diagnostic experiment, not a production fix.

A privacy-safe derived summary is in
[the Latitude 7390 evidence record](docs/evidence/latitude-7390-0a5c-5833.md).
Raw payloads and hardware logs are not published.

## Safety boundary

None of the documented bring-up commands install files into the running system.
The scripts do not call `sudo`, `pacman`, `systemctl`, or `udevadm trigger`, and
do not alter PAM or authentication.

`install.sh` retains its historical name but is now only a repository-local
`DESTDIR` staging tool. It refuses destinations outside `./stage`.

## Staged USB probe

Create a repository-local Python environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-probe.txt
.venv/bin/python -m unittest discover -s tests -v
```

Run each hardware stage separately:

```sh
# No interface claim and no transfer
.venv/bin/python docs/cv_usb_probe.py --pid 5833 --stage enumerate

# Claim and release interface 0; no transfer
.venv/bin/python docs/cv_usb_probe.py --pid 5833 --stage open

# Send exactly one allow-listed get-version command
.venv/bin/python docs/cv_usb_probe.py \
  --pid 5833 --stage command --command get-version
```

Other commands are blocked unless
`--allow-stateful-command` is explicitly supplied.
Payload bytes are redacted by default. `--show-payload` is intended only for
private diagnosis; logs containing device payloads must not be published.

## Build the probe-only plugin

The source branch, source commit, and stock binary SHA-256 are pinned. The
build aborts if Canonical's source changes before it is reviewed.

```sh
./build_from_upstream.sh --target-pid 5833 --patch-set probe
```

The output is:

```text
prebuilt/libfprint-2-tod-1-broadcom-5833.probe.so
```

`probe` applies patches 1-3 only. It intentionally leaves the original
enrollment and verification code unchanged. See [PATCHES.md](PATCHES.md).

## Repository-local TOD integration test

Stock Arch `libfprint` does not provide the `libfprint-2-tod.so.1` ABI required
by the proprietary plugin. The test environment therefore builds the
`v1.95.2+tod1` loader entirely under `.local-test/`; it does not install or
replace an Arch package.

```sh
tools/prepare_local_tod_test.sh

tools/run_local_tod_test.sh --stage load
tools/run_local_tod_test.sh --stage probe
tools/run_local_tod_test.sh --stage open
```

The stages are intentionally separate:

- `load` loads the plugin and prints the runtime driver/USB ID table without
  USB enumeration.
- `probe` enumerates USB and succeeds only if the Broadcom device survives the
  driver's async probe.
- `open` performs the same probe, then public TOD open and close operations.

Each runner has a 20-second timeout and writes an ignored log under
`test-results/`.

On Arch systems where runtime GLib is installed but the `glib-mkenums` build
tool is absent, the preparation script fetches the exact installed GLib tag and
generates that tool under `.local-test/`. It never writes `/usr/bin`.

## Arch/CachyOS staging

Validate and mirror the Arch filesystem layout under the repository:

```sh
packaging/arch/stage.sh
```

This produces:

```text
stage/arch/usr/lib/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so
stage/arch/usr/lib/udev/rules.d/60-libfprint-2-tod1-broadcom-cv2.rules
```

No rule is loaded and no plugin is installed. See
[packaging/arch/README.md](packaging/arch/README.md).

For other distributions, `install.sh --help` exposes relative `--libdir` and
`--udevdir` staging parameters instead of assuming Ubuntu's multiarch paths.

## Repository layout

```text
build_from_upstream.sh       pinned stock fetch + repository-local build
patch_driver.py              PID-aware probe/full byte patcher
docs/cv_usb_probe.py         staged raw USB transport probe
tests/                       patcher and packet unit tests
tools/cv_tod_probe.c         minimal public libfprint probe/open harness
tools/prepare_local_tod_test.sh
tools/run_local_tod_test.sh
udev/                        rules for validated CV2 PIDs
packaging/arch/              Arch-only repository staging
PATCHES.md                   patch rationale and observed evidence
docs/controlvault2-command-status-reference.md
                             inferred command/status dictionary
```

## Known limitation

The proprietary plugin reports a CV3 chip-type error (`0x1c`) on BCM5880 after
a successful `cv_get_ush_ver`. Probe patch 3 routes that known CV2 condition to
the driver's success path. This is justified by the observed device response,
but it does not prove that every higher-level enrollment or matching status is
identical between `5833` and `5834`.

The experimental enrollment harness is repository-local, opt-in, and
fail-closed. It preserves the observed `0x89` re-arm behavior and performs at
most one diagnostic repeated update after `0x59`. It does not implement the
missing BCM5880 host-side completion coordinator. Patch 4 is not enabled for
the tested `5833` profile.

## Research scope

This repository contains independently derived interoperability research for
Linux support of lawfully owned Broadcom ControlVault2 hardware.

Command names marked as inferred are not official Broadcom terminology.

No proprietary binaries, firmware, cryptographic keys, raw fingerprint
features, biometric templates, personal identifiers, or authentication
credentials are included.

## License and redistribution

The scripts, tests, rules, and documentation are MIT licensed. The Broadcom TOD
driver and firmware are proprietary and are not covered by that license. A
public fork should ship only the patching/build machinery and let users fetch
the pinned stock binary from Canonical.
