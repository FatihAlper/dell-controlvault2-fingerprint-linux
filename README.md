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
| Bounded `0x59` diagnostic | A single repeated update returns `0x89`; Windows controls do not use this retry |
| Fresh-boundary diagnostic | One accepted update was followed by fresh `0x66`, but no between-capture `0x8a`; later touches did not complete |
| CaptureGetResult diagnostic | Selector `1` was called once after capture; native `0x89`, `0x17000` length unchanged; payload redacted and wiped |
| Enrollment completion | Incomplete; completion remains zero |
| Commit and verify | Not proven |

Capture and retry recovery work on the tested BCM5880 device, but enrollment
completion, template commit, and verification remain incomplete. The bounded
`0x59` retry is a diagnostic experiment, not a production fix. Windows runtime
controls show both a successful four-`0x6c` path and two failed paths where the
fourth `0x6c` receives a shorter protected reply followed by `0x6d` discard.

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
tools/compare_cv_usb_updates.py
                             payload-redacting UpdateEnrollment comparison
tools/audit_windows_a21_update.py
                             read-only A21 cross-adapter dataflow validator
tools/windows_a21_enrollment_trace.js
                             payload-free A21 enrollment metadata tracer
tools/run_windows_a21_enrollment_trace.ps1
                             hash-pinned Windows tracer runner
tools/audit_linux_bcm5880_abis.py
                             read-only pinned Linux export ABI validator
tools/run_capture_get_result_probe.sh
                             one-call, payload-redacting capture-result probe
tools/bcm5880_enrollment_coordinator.[ch]
                             compile-gated mock-only 3+1 coordinator core
tools/bcm5880_linux_abi_adapter.[ch]
                             mock-only five/eleven-argument ABI adapter
udev/                        rules for validated CV2 PIDs
packaging/arch/              Arch-only repository staging
PATCHES.md                   patch rationale and observed evidence
docs/controlvault2-command-status-reference.md
                             inferred command/status dictionary
```

The capture-result experiment and its strict no-update/no-template/no-commit
boundary are documented in
[the CaptureGetResult evidence note](docs/evidence/capture-get-result-probe.md).
The next Windows reference experiment and its no-payload/no-memory-write
boundary are documented in
[the A21 enrollment metadata trace](docs/evidence/windows-a21-enrollment-metadata-trace.md).

## Known limitation

The proprietary plugin reports a CV3 chip-type error (`0x1c`) on BCM5880 after
a successful `cv_get_ush_ver`. Probe patch 3 routes that known CV2 condition to
the driver's success path. This is justified by the observed device response,
but it does not prove that every higher-level enrollment or matching status is
identical between `5833` and `5834`.

The experimental enrollment harness is repository-local, opt-in, and
fail-closed. Its historical default preserves the observed `0x89` re-arm
behavior and performs at most one diagnostic repeated update after `0x59`.
The preferred next-test mode disables that replay and blocks native completion
before generic commit:

```sh
tools/run_local_enrollment_0x89_test.sh \
  --confirm-real-enrollment --fresh-boundary
```

The fresh-boundary policy was run once on hardware. It reached `1/10`, issued
a fresh `0x66`, and then waited without completing another capture despite
four lift-and-touch attempts. The trace had no `0x8a` between the accepted
incomplete update and that fresh capture, unlike the successful Windows
control. No `0x6e` or `0x6f` commit command was reached, and the device stayed
at `0a5c:5833`. The next candidate is a separately tested re-arm after native
success with completion zero. Patch 4 is not enabled for the tested `5833`
profile.

The separately selected follow-up mode adds one native `0x8a` after accepted
status-zero/completion-zero progress and stops before a fourth incomplete
acceptance can schedule another capture:

```sh
tools/run_local_enrollment_0x89_test.sh \
  --confirm-real-enrollment --fresh-rearm-boundary
```

Call-level provenance can be recorded without pointer addresses or buffer
contents by adding `--trace-update-metadata`. The trace is opt-in and does not
change native statuses or add another interposed function.

It is covered by mock tests. Its first hardware control produced five native
`0x89` quality rejections, each with successful normal re-arm, so the new
accepted-incomplete branch was not exercised. Cancellation and close completed
cleanly; no commit command was reached and the device stayed at `0a5c:5833`.

A second hardware control exercised that branch three times. Each accepted
status-zero/completion-zero update was followed by native `0x8a`, and every
following fresh `0x66` capture completed instead of hanging. The next update,
at the four-update boundary, still returned native `0x59`. The policy preserved
that result without replay, synthesis, state forcing, or commit; stock cleanup
closed the device cleanly. This separates the missing between-capture re-arm
from the still-unresolved fourth-update boundary.

An independent 2026-08-19 replication produced the same decisive sequence:
three accepted status-zero/completion-zero updates, each followed by successful
native `0x8a` and a completed fresh capture, then native `0x59` on the next
update. Its USB trace contained eight `0x66`, eight `0x6c`, and eight `0x8a`
request/response pairs with zero packet loss. Four intervening `0x89` quality
retries were preserved. The run again stopped before replay or commit and
closed the device cleanly.

Offline comparison of the two Linux controls and three Windows controls found
that every Linux `0x6c` carried the fresh 20-byte value from its immediately
preceding `0x66` response, including the update that returned `0x59`. Windows
success and failure used the same four-request transport shape and first
diverged at the fourth response length. See
[the privacy-safe structural comparison](docs/evidence/update-enrollment-structural-comparison.md).

A follow-up call-level trace confirmed that every accepted Linux update writes
a nonzero 20-byte output, but the next update receives a new zeroed output
buffer, zero auxiliary-input length, and a fresh capture ID that does not match
the previous output. The final `0x59` writes none of its output fields. See
[the redacted metadata evidence](docs/evidence/update-enrollment-call-metadata.md).

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
