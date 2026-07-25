# Reverse-engineering notes and patch rationale

Command/status names in this document are inferred unless an evidence section
explicitly says otherwise. See
[`docs/controlvault2-command-status-reference.md`](docs/controlvault2-command-status-reference.md)
for confidence and provenance.

## Devices and scope

The original project targets ControlVault 2 / BCM5880 USB ID `0a5c:5834`.
This branch adds a separately selectable `0a5c:5833` target.

The tested `5833` device on a Dell Latitude 7390 exposes interface 0 with:

- bulk OUT `0x01`
- bulk IN `0x81`
- interrupt IN `0x85`

That endpoint equality alone suggested a shared transport but was not treated
as proof of protocol compatibility.

## Observed 5833 protocol evidence

The staged raw probe sent one 44-byte `cv_get_ush_ver` command (`0x39`) to
endpoint `0x01`.

Observed sequence:

1. The complete 44-byte request was accepted.
2. Interrupt endpoint `0x85` returned an 8-byte completion response.
3. Bulk endpoint `0x81` returned a 44-byte encapsulated response with command
   ID `0x39`.
4. The proprietary driver's own probe later logged
   `cv_get_ush_ver() status: (0x0)`.

This proves that `5833` implements the command framing and completion/bulk
response flow expected by this ControlVault driver. Fields whose semantics
have not been established are intentionally not assigned guessed meanings.
Raw request and response payloads are retained locally and are not published.

## Stock binary identity

The patcher is tested against Canonical's `upstream` branch:

```text
commit: f7d31fcb9f6952d7d76ba50287e000c29760589d
stock SHA-256: 54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172
ELF Build ID: 66134403db205c7c1ac682885229224790aedc0e
```

`build_from_upstream.sh` rejects a different commit or binary checksum. The
patcher additionally requires every byte signature to occur exactly once.

## Patch sets

`patch_driver.py` exposes two explicit sets:

- `probe`: patches 1-3 only
- `full`: patches 1-5, retaining the original project's enrollment/verify
  experiments

The `5833` validation uses only `probe`. Both the patcher and build wrapper
reject `5833/full`; legacy patches 4 and 5 remain available only for the
project's original `5834` target.

| # | Site | Change | Technical reason |
|---|---|---|---|
| 1 | `.rodata` ID table | CV3 PID `0x5842` → selected CV2 PID (`0x5833` or `0x5834`) | Lets the TOD loader bind the selected device to `Broadcom Sensors`. |
| 2 | internal USB enumerator | conditional PID branch `0x74` → unconditional branch `0xeb` | The plugin has a second CV3-only PID gate after libfprint binding. The public ID table from patch 1 remains the outer device-selection boundary. |
| 3 | `dev_probe` | error `0x1c` branch displacement `0x1f` → `0x3a` | On tested `5833`, the CV command succeeds (`0x0`) and then CV3 chip classification returns `0x1c`. BCM5880 is CV2, so the CV3 firmware classification cannot identify it. Routing this observed condition to completion lets probe finish without flashing firmware. |
| 4 | enroll state machine | status `0xa4` comparison/path → original project's CV2 `0x59` path | Existing `5834` enrollment experiment; not included in the `5833` probe artifact and not validated on `5833`. |
| 5 | verify completion | remove `edx != 0` short-circuit | Existing `5834` verification experiment; not included in the `5833` probe artifact and not validated on `5833`. |

For the pinned stock binary, probe patch offsets are:

```text
1: 0x2f620
2: 0x28403
3: 0x0d1b8
```

Offsets are evidence only. Application is signature-based and
offset-independent.

## Runtime probe evidence

Using a repository-local build of `libfprint-tod` `v1.95.2+tod1`:

```text
Loading driver broadcom (Broadcom Sensors)
Supported Devices: ..., 0a5c:5833, ...
dev_probe() called
cv_get_ush_ver() status: (0x0)
Could not determine chip type
FwUpgradeError ... Error: 0x1c
Device reported probe completion
```

The resulting `FpContext` contains one `broadcom` device. Public
`fp_device_open_sync` and `fp_device_close_sync` also complete. No
enrollment, verify, identify, list, delete, authentication, PAM, or login call
is part of this test.

## Remaining uncertainty

The evidence is sufficient to conclude that `5833` is supportable through
plugin load, transport, probe, open, and close. It is not sufficient to claim
that template storage or match-on-chip status codes are identical to `5834`.
Those phases require a separate, explicitly authorized test plan.
