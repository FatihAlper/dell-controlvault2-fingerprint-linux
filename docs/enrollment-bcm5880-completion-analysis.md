# BCM5880 host-side enrollment completion analysis

## Scope and binary identities

This is a read-only static analysis of the missing BCM5880 enrollment
completion path. No driver, interposer, fixture, firmware, or proprietary
binary was changed; no build or hardware test was run.

Inputs:

| Artifact | Identity |
|---|---|
| Linux probe-only TOD DSO | `prebuilt/libfprint-2-tod-1-broadcom-5833.probe.so` |
| Linux SHA-256 | `c7dbb44e25aa5127515cb4de23868358d7b170d2625227131a88bce39f3e8ef6` |
| Linux Build ID | `66134403db205c7c1ac682885229224790aedc0e` |
| Dell A21 package | Ephemeral hash-verified extraction; not distributed |
| Dell package SHA-256 | `e157fbe548bfd2b6b1ee4410b5dc93255409b329bbe4d75da9d7c1684fa1db4e` |
| Windows library | `drivers/production/Windows10-x64/CV/bin/bipdll.dll` |
| `bipdll.dll` SHA-256 | `30c556a9b542d0fcf29a6822b3bb81fe23ce2917b403b3f25af9384e0e31e524` |
| Hardware evidence | Privacy-safe derived summary; raw log retained locally |

For `bipdll.dll`, image base is `0x180000000`. Its `.text` section has RVA
`0x1000` and file offset `0x400`, so a `.text` instruction's file offset is
`RVA - 0xc00`. The zero-filled globals below have virtual addresses but no
individual on-disk file offsets.

## Hardware interpretation

The accepted progress sequence is:

```text
1, 2, 3,
0x59 -> second 0x6c = 0x89 -> 0x8a -> capture,
4, 5, 6,
0x59 -> second 0x6c = 0x89 -> 0x8a -> capture,
7, 8, 9,
0x59 -> second 0x6c = 0x89 -> 0x8a -> capture,
10, 11, 12,
0x59 -> second 0x6c = 0x89 -> 0x8a -> capture,
13
```

The four first `0x59` results occur on UpdateEnrollment calls beginning at
approximately `01:44:16.232`, `01:45:13.607`, `01:45:45.881`, and
`01:46:11.225`. They follow accepted counts 3, 6, 9, and 12. Each bounded
second call returned native `0x89`; each corresponding `0x8a` succeeded.

Every accepted progress event followed:

```text
real update status 0x00
  -> completion byte 0x00
  -> Linux wrapper synthesizes 0x8f
  -> outer callback increments its host counter
```

The evidence log's `Update enrollment is successful` and `More fingers
needed` messages are the status-zero/completion-zero block at Linux RVAs
`0x2b1a0`--`0x2b1f6`. Therefore an accepted progress event does not prove a
firmware completion transition.

### Why 10/10 is not a device threshold

The Linux class initializer hard-codes the two class fields at RVA/file
offset `0xd2bc`:

```asm
movabs rax,0x10000000a
mov    [rbx+0xa8],rax
```

The low dword is the libfprint enrollment stage count `10`; the following
dword is `1`. No firmware response supplies the number ten.

The outer callback increments the driver-private counter at `device+0x20`:

```asm
0xdf50 mov eax,[rbx+0x20]
0xdf53 lea esi,[rax+1]
0xdf56 mov [rbx+0x20],esi
```

The `cmp esi,9` at `0xdf59` only suppresses the driver's internal percentage
message above nine. Both branches still call
`fpi_device_enroll_progress` and requeue state 1 at `0xdf5e`--`0xdf6d`.
There is no cap or completion test against ten. Consequently 11/10--13/10
are host counter overrun caused by continued accepted status-zero,
completion-zero samples.

### Exact missing Linux transition

The Linux raw update succeeds only when command `0x6c` returns zero. Its
success block writes the completion output at `0x263a0`. The TOD wrapper
then tests that byte:

```asm
0x2b14d test r12d,r12d       ; native status
0x2b150 je   0x2b1a0
0x2b1b3 cmp  byte [rsp+0xb],0
0x2b1b8 je   0x2b1e8         ; completion zero -> synthetic 0x8f
```

Only native status `0x00` plus a nonzero completion byte reaches the outer
callback as status `0x00`. In task state 1:

```asm
0xdd27 test r13d,r13d
0xdd2a jne  0xdf78
0xdd38 cmp  eax,1
0xdd3b je   0xe010
0xe010 mov  dword [device+0x24],2
```

The task's 20-byte enrollment output is copied to `device+0x34` at
`0xe017`--`0xe026`, and state 2 is queued. The state-2 worker at
`0xcb10` calls `cvif_fingerprint_commit_enrollment` at `0xcb2d`; the generic
Linux commit function builds command `0x6e` at `0x2691d`.

Thus the absent condition is not “progress reaches ten.” It is a successful
BCM5880 host processing operation which returns native zero, writes
completion one, creates a valid 20-byte enrollment token, and retains the
template state required by the matching commit implementation.

## Windows BCM5880 selector

The exported Windows `cv_fingerprint_update_enrollment` dispatcher begins at
RVA `0x2d110` (file `0x2c510`). Its selector and branch are:

| RVA | File | Instruction | Effect |
|---:|---:|---|---|
| `0x2d242` | `0x2c642` | `call 0x4ae70` | Call the internal `is5880` selector. |
| `0x2d249` | `0x2c649` | `test al,al` | Test the cached result. |
| `0x2d24b` | `0x2c64b` | `je 0x2d266` | False selects generic command `0x6c`. |
| `0x2d256` | `0x2c656` | `call 0x2cef0` | True selects `cvFingerprintUpdateEnrollment5880`. |

`is5880`, RVA `0x4ae70` (file `0x4a270`), does not inspect USB PID,
chip-type constant `0x1c`, capture mode `0x23`, registry, INF, SMBIOS, or
ACPI data. It:

1. checks a cached-result-valid byte at shared RVA `0xaf00e`;
2. obtains an `0x800`-byte `cv_get_ush_ver` text result through the call at
   RVA `0x4aebc` (file `0x4a2bc`);
3. searches it for the literal `USH_CHIPID:5880` at RVA `0x4aef9`
   (file `0x4a2f9`);
4. writes the cached true result at RVA `0x4af15` (file `0x4a315`);
5. caches that the check ran at RVA `0x4af9a`.

The additional open/status/close calls at RVAs `0x4af2f`, `0x4af58`, and
`0x4af75` obtain a timeout/status value but do not change a true result back
to false on their logged error exits.

This proves that selection is a Windows host-library decision based on the
device-reported USH version string. Static analysis cannot prove the string
returned on this Latitude 7390. USB PID `0x5833` versus `0x5834` is not part
of this selector; the two PIDs select alike only if both return the same
`USH_CHIPID:5880` text. The hardware model and repeated three-sample boundary
make the true branch likely for this machine, but a Windows runtime trace is
still required to prove it.

## Windows `cvFingerprintUpdateEnrollment5880` prototype

The helper begins at RVA `0x2cef0` (file `0x2c2f0`) and uses the Windows x64
calling convention:

```c
uint32_t cvFingerprintUpdateEnrollment5880(
    uint32_t handle,                    /* ecx */
    const uint8_t enrollment_id[20],    /* rdx */
    uint8_t *completion_out,            /* r8 */
    uint8_t enrollment_data_out[20]);   /* r9 */
```

The generic seven-argument update dispatcher passes only these four values
to the selected helper. In particular, the optional update input and
`output_value_out` are not passed. Therefore this helper cannot produce the
generic update's 4-byte output value.

## Full BCM5880 update CFG

### Guards and context validation

| RVA / file | Basic block and branch | Result |
|---|---|---|
| `0x2cf0a` / `0x2c30a` | completion flag `[0xaf007] != 0` | Return `0x8c`. |
| `0x2cf26` / `0x2c326` | capture-valid `[0xaf000] == 0` | Return `0x89`. |
| `0x2cf41`--`0x2cf68` / `0x2c341`--`0x2c368` | elapsed tick exceeds `[0xaf018]` | Clear capture-valid and return `0x89`. |
| `0x2cf72`--`0x2cf9c` / `0x2c372`--`0x2c39c` | compare input ID with `[0xaf030..0xaf043]` | Mismatch returns `0x88`. |
| `0x2cfb0` / `0x2c3b0` | `mov byte [r14],0` | Initialize caller completion to zero. |
| `0x2cfb3` / `0x2c3b3` | `cmp esi,3` | `count < 3` accumulates; `count >= 3` processes. |

The 20-byte session/capture enrollment ID in shared RVAs
`0xaf030..0xaf043` is created in the enrollment-capture setup block at
RVA `0x2b222`, copied to the caller at `0x2b248`--`0x2b25d`, and validated
on every selected update. The RNG wrapper at RVA `0x51f58` initializes a
dword and requests exactly four random bytes.

### First three selected updates

The state is process-global, not a heap enrollment-context object:

| Global RVA | Size | Purpose |
|---:|---:|---|
| `0x8e614` | 4 | Buffered feature count. |
| `0x8e638` | 12 | Three variable feature lengths. |
| `0x8e660` | `3 * 0x258 = 0x708` | Three feature slots, stride/capacity 600 bytes each. |
| `0x8e608` | 4 | Current captured feature length. |
| `[0x8ce48]+4` | variable | Current captured feature bytes. |

For count zero, one, and two:

```text
0x2cfb8 load current length
0x2cfcf destination = 0x8e660 + count * 0x258
0x2cfdd memcpy(destination, [0x8ce48]+4, current_length)
0x2cfe2 store current_length at 0x8e638[count]
0x2cfec increment count
0x2cfee store count
0x2cff4 return 0x00, completion still 0
```

The record is variable length; `0x258` is the slot stride/capacity, not proof
that every feature is exactly 600 bytes. This helper contains no explicit
`current_length <= 0x258` check, so that invariant must be supplied by the
capture producer.

The current feature is produced by the Windows asynchronous capture path.
The worker at RVA `0x2ac30` chooses a result buffer, places the maximum
length at global `0x8e608`, and calls exported
`cv_fingerprint_capture` at RVA `0x26d10` from RVA `0x2ad5b`. The capture
function updates the length and bytes. This is the data source absent from
the Linux TOD enrollment orchestration.

### Fourth selected update

When the saved count is at least three, the fourth current feature remains
in the live capture buffer and is not copied into a fourth slot. The call at
RVA `0x2d084` (file `0x2c484`) invokes exported
`cv_fingerprint_create_template`, RVA `0x2e0c0` (file `0x2d4c0`), with four
feature pairs:

| Feature | Length | Data |
|---|---|---|
| 0 | `[0x8e638]` | `0x8e660` |
| 1 | `[0x8e63c]` | `0x8e8b8` (`0x8e660 + 0x258`) |
| 2 | `[0x8e640]` | `0x8eb10` (`0x8e660 + 2*0x258`) |
| 3 | `[0x8e608]` | `[0x8ce48]+4` |

Before the call, RVA `0x2d073` resets the feature count to zero and RVA
`0x2d07a` sets template output capacity `[0x8ce38]` to `0x708`.
The template output buffer is `[0x8ce08]+4`; the initialized pointer at
`0x8ce08` targets a library-owned static buffer.

`cv_fingerprint_create_template` validates four nonempty feature inputs and
the output capacity, marshals five input/output parameter records, and builds
CV command `0x6f` at RVA `0x2e49d` (file `0x2d89d`). It accepts native
success (and has special handling for `0x34`) and saves the returned template
length and bytes.

Back in the selected update helper:

| RVA / file | Instruction | Meaning |
|---|---|---|
| `0x2d08c` / `0x2c48c` | `test eax,eax; jne 0x2d0d5` | Only template-create status zero continues. |
| `0x2d097` / `0x2c497` | `mov byte [0xaf007],1` | Mark host-side enrollment template ready. |
| `0x2d09e` / `0x2c49e` | `mov byte [r14],1` | Exact caller completion-byte write. |
| `0x2d0a2` / `0x2c4a2` | `call 0x51f58` | Generate a 4-byte opaque enrollment token prefix. |
| `0x2d0c1`--`0x2d0d2` / `0x2c4c1`--`0x2c4d2` | copy 20 bytes from `0x8e648` | Fill `enrollment_data_out`. |

The direct fourth-update call graph is:

```text
cvFingerprintUpdateEnrollment5880 (0x2cef0)
  -> cv_fingerprint_create_template (0x2e0c0)
       -> parameter marshaling helpers (0x48800)
       -> CV transport (0x37990), command 0x6f
       -> return-value extraction
  -> four-byte RNG wrapper (0x51f58)
       -> random-byte provider (0x62ed0)
  -> 20-byte token copy
```

There is no call to `cv_fingerprint_enroll_dup_check` in this CFG. Command
`0x6f` may itself return policy-related statuses, but static evidence does
not justify calling that an explicit duplicate check.

### Exact completion condition

Completion one requires all of these conditions:

1. the dispatcher selected the 5880 helper;
2. no template is already marked complete;
3. a current capture is valid and within its allowed time;
4. the supplied 20-byte enrollment/capture ID matches;
5. three features have already been buffered;
6. a fourth current feature is available;
7. `cv_fingerprint_create_template`/command `0x6f` returns `0x00`.

Only then do RVAs `0x2d097` and `0x2d09e` write the ready flag and completion
byte. The later RNG call is not part of the completion condition: RNG
failure is logged but the code still copies the token storage and returns
the successful template-create status.

This makes the best completion classification **G: multiple conditions**,
specifically A + B + E + F from the candidate list, with command-`0x6f`
success as an additional required firmware result. A bare sample count, a
bare `0x59`, or a forced completion byte is insufficient.

## Enrollment output and commit state

The selected update's 20-byte output is not the template. It is an opaque
token copied from global `0x8e648..0x8e65b`. The helper calls an RNG wrapper
which writes exactly four bytes at `0x8e648`. The remaining 16 bytes are in
zero-filled image storage and have no other direct writer in the recovered
CFG. This strongly suggests a 4-byte random token followed by zero padding,
but indirect writes outside the recovered call graph cannot be excluded.

The real template is held separately:

| Field | Storage |
|---|---|
| Template length | `[0x8ce38]` |
| Template bytes | `[0x8ce08]+4` |
| Template-ready flag | shared byte `0xaf007` |
| Commit token | `0x8e648..0x8e65b` |

The Windows exported `cv_fingerprint_commit_enrollment` at RVA `0x2da30`
calls the same `is5880` selector at RVA `0x2db75` (file `0x2cf75`). A true
result calls the selected commit helper at RVA `0x2dbaf` (file `0x2cfaf`);
it does not enter the generic commit branch.

The selected commit helper at RVA `0x2d8f0` (file `0x2ccf0`):

- returns `0x8d` if the template-ready flag is zero;
- compares the supplied 20-byte token with `0x8e648..0x8e65b`, returning
  `0x8e` on mismatch;
- uses the retained template length and buffer;
- clears the ready flag and sample count;
- calls the WBF/template commit helper at RVA `0x2f780`.

That helper constructs a different host/template operation (the call at RVA
`0x2fba5` uses an internal command selector with word `0x09`), not the
generic CV command `0x6e` path. Therefore Windows 5880 completion does
**not** merely prepare a 20-byte value for generic `0x6e`; update and commit
are a matched pair of special host-side paths.

The selected discard path also differs. At RVA `0x2d783` (file `0x2cb83`)
the same selector is called; on true, RVAs `0x2d78c` and `0x2d792` clear the
feature count and ready flag and return without issuing generic command
`0x6d`. The generic false branch builds `0x6d` at RVA `0x2d7dc`.

The selected helper uses process-global and shared globals without an
internal lock. Its safe ownership model therefore depends on serialized
adapter operations. It is not independently thread-safe or suitable for
parallel enrollment sessions.

## Reconstructed layouts

### Windows selected path

| Object/field | Offset or RVA | Size | Initial/success value | Lifetime/cleanup |
|---|---:|---:|---|---|
| Current capture valid | shared `0xaf000` | 1 | 0 / 1 | Cleared by result retrieval/timeout. |
| Template ready | shared `0xaf007` | 1 | 0 / 1 | Cleared by selected discard or commit. |
| Capture start tick | shared `0xaf014` | 4 | tick value | Per current capture. |
| Allowed interval | shared `0xaf018` | 4 | device-status derived | Cached process-wide. |
| Enrollment/capture ID | shared `0xaf030` | 20 | RNG prefix plus retained bytes | Valid for the selected enrollment/capture session. |
| Current feature length | `0x8e608` | 4 | capture capacity, then actual length | Reused each capture. |
| Buffered count | `0x8e614` | 4 | 0 / 1..3 / reset 0 | Reset on processing, discard, and commit. |
| Buffered lengths | `0x8e638` | 12 | three dwords | Process-global enrollment state. |
| Commit token | `0x8e648` | 20 | zero-filled / RNG prefix | Created after template success; checked by commit. |
| Feature slots | `0x8e660` | `0x708` | three variable records | Process-global; logical validity governed by count. |
| Current feature buffer | `[0x8ce48]+4` | variable | capture result | Library-owned static buffer. |
| Template capacity/length | `0x8ce38` | 4 | `0x708` / returned size | Retained through selected commit. |
| Template buffer | `[0x8ce08]+4` | variable | command `0x6f` output | Retained through selected commit. |
| Caller completion | helper arg 3 | 1 consumed | 0 / 1 | Caller-owned. |
| Caller enrollment data | helper arg 4 | 20 | commit token | Caller-owned copy. |

### Linux TOD task and device state

| Object/field | Offset | Size | Use |
|---|---:|---:|---|
| Task state | task `+0x04` | 4 | 0=start, 1=capture/update, 2=commit. |
| Capture/enrollment ID | task `+0x08` | 20 | Passed to capture and update. |
| Enrollment output | task `+0x1c` | 20 | Raw update output; passed to commit. |
| Update output value | task `+0x30` | 4 | Raw update output; later passed through commit wrapper. |
| Task status | task `+0x34` | 4 | Callback dispatch status. |
| Accepted counter | device `+0x20` | 4 | Incremented only for synthetic `0x8f`. |
| Enrollment state | device `+0x24` | 4 | State 1 persists until native-zero/completion-nonzero. |
| Persisted enrollment token | device `+0x34` | 20 | Copied on state-1 completion. |

The Linux raw update only clears and writes its three outputs on a native
success path at RVAs `0x26330`--`0x263a0`. Native `0x59` and `0x89` branch
at `0x2632a` directly to cleanup, leaving the caller storage unchanged.

The wrapper initializes only the completion byte at RVA `0x2b117`. It does
not initialize its 4-byte stack output before calling the raw function.
Consequently the observed `output_value_out = 0x00007fc3` after nonzero
statuses is uninitialized stack residue, not a firmware value, length,
capability, bitmask, pointer, status, or proven metadata. Repetition of the
same residue reflects stack reuse. It must not be used as a commit invariant.

## Linux dormant 5880 functionality

The probe-only ELF contains an exported `is5880` at RVA/file `0xfed0`:

```asm
0xfed0 endbr64
0xfed4 xor eax,eax
0xfed6 ret
```

It is an unconditional false stub, not a missing initialization read. There
are no call relocations or direct calls to it in this DSO.

The following named BSS symbols exist:

| Symbol | RVA | Size | Static references |
|---|---:|---:|---|
| `captureIDLocal5880` | `0x3fc90` | 20 | None found. |
| `captureCompletionStatus5880` | `0x3fc88` | 4 | None found. |
| `is5880Device` | `0x3fcb0` | 1 | None found. |
| `captureIDRestart` | `0x3fc70` | 20 | Generic capture-start copy at `0x2558e`. |
| `cvFPRestartPending` | `0x3fc84` | 1 | Generic capture-cancel clear at `0x257af`. |

The last two names are active generic restart/cancel plumbing; they do not
implement Windows feature accumulation. The first three are orphaned
globals in this build.

No internal call or relocation targets:

- `is5880`;
- `cv_fingerprint_capture_get_result`;
- `cv_fingerprint_create_template`;
- `cv_fingerprint_create_feature_set`; or
- `cv_fingerprint_commit_feature_set`

from the TOD enrollment state machine. There is no three-slot `0x258`
accumulator, selected update helper, host-side completion writer, commit
token generator, or selected commit dispatcher in the Linux DSO.

The only completion output writes in Linux `cv_fingerprint_update_enrollment`
are the initial zero at RVA `0x26338` and the byte copied from the native
command return list at RVA `0x263a0`. The wrapper only reads that byte. No
Linux host-side enrollment path writes literal one to it.

Linux does contain the reusable low-level primitive
`cv_fingerprint_create_template` at RVA/file `0x26d10`. It validates four
feature records and emits command `0x6f` at `0x2703d`, matching the Windows
primitive structurally. This proves the firmware-facing template-create
primitive is present. It does not solve how the TOD path obtains and owns
the four feature records, and it does not provide the selected Windows
commit-state machinery.

Therefore the Windows selected path is not “present but unreachable” as a
complete unit in Linux. Only several generic primitives and leftover names
are present; the required host orchestration is absent.

## Comparison with patch 4

Patch 4 changes at Linux RVA/file `0xdd0d`:

```text
original bytes:
41 81 fd a4 00 00 00 0f 84 fd 01 00 00

replacement bytes:
41 81 fd 59 00 00 00 0f 84 16 00 00 00
```

It changes:

```asm
cmp r13d,0xa4 ; je 0xdf17
```

to:

```asm
cmp r13d,0x59 ; je 0xdd30
```

For task state 1 this routes `0x59` through the status-zero state dispatcher,
sets state 2, and lets the next worker invoke generic command `0x6e`. It
does not create a completion byte, capture feature blobs, call command
`0x6f`, fill a native enrollment token, retain a template, or select a
matching 5880 commit helper.

On the observed native `0x59` path, `enrollment_data_out` is still twenty
zero bytes and `output_value_out` is uninitialized stack residue. Patch 4
therefore reaches generic commit without the invariants established by the
Windows selected path. This can plausibly explain historical `0x8d` or
`0x24` commit failures, but no current hardware trace proves the causal
mapping of either status.

Patch 4 may appear to make progress because it performs one correct
high-level action—leaving update state and entering a commit phase at the
three-sample boundary—but it chooses the generic Linux commit mechanism
without the selected path's data and retained state. It also removes
`0xa4`'s retry handling, an independent regression.

## Most likely missing component

The highest-confidence answer is:

> Linux lacks the BCM5880 host-side enrollment transaction coordinator:
> it must retrieve each capture's feature blob, retain three variable-length
> features, combine those three plus the fourth live feature through the
> existing `cv_fingerprint_create_template`/`0x6f` primitive, retain the
> resulting template and template-ready state, create the 20-byte commit
> token, set completion one only after template creation succeeds, and use
> a matching BCM5880 host-template commit path rather than blindly issuing
> generic `0x6e`.

This is proven as the behavior of the A21 Windows selected path and proven
absent as an integrated path in the Linux DSO. That the Latitude 7390 would
select this Windows path at runtime remains a strong inference rather than
runtime proof.

## Ranked solution options

### 1. Reuse exported Linux primitives with a clean host coordinator

Rank: first.

Feasibility is medium. Linux exports capture-result and
`cv_fingerprint_create_template` primitives, and the latter emits the needed
`0x6f`. Unknowns are the exact capture mode/result buffer contract, maximum
feature length, selected commit helper equivalent, token format, and cleanup
ordering. Data corruption risk is manageable only with strict length,
session-ID, and lifecycle validation. An interposer can prototype update
coordination, but safely testing commit likely requires a repository-local
host coordinator rather than forcing the existing generic state.

### 2. Clean-room implementation of the minimum Windows host path

Rank: second.

Feasibility is medium-low but suitable for a permanent source driver. It
requires reconstructing the feature acquisition ABI and the special commit
operation, not copying proprietary code. It offers explicit ownership,
locking, bounds, cancellation, and fail-closed behavior. Template corruption
risk is high until the selected commit payload and storage invariants are
proven.

### 3. Enable an existing complete Linux 5880 path

Rank: third because the required path was not found.

The Linux binary has an `is5880` false stub, orphaned 5880 globals, and
low-level helpers, but no selected update/commit coordinator or three-feature
buffer. Changing the stub cannot activate code which is absent. This option
becomes viable only if another Broadcom Linux build containing the complete
path is located and binary-diffed.

### 4. Force completion or state 2

Rank: unsafe; reject.

Current hardware evidence proves completion zero, enrollment output zero,
and a stale 4-byte output. Forcing completion or state 2 would invoke generic
commit without a created/retained template and without a valid matched token.
This has the highest template corruption and commit-state risk and does not
reproduce Windows.

## Minimal next experiment design — not implemented

The next experiment should answer only whether the native Linux primitives
can reproduce the selected update half safely. It must not commit.

1. Interpose the enrollment capture/update boundary, not generic commit.
2. Obtain each current feature through a proven native capture-result API;
   do not infer bytes from `0x59` output buffers.
3. Validate the feature length is nonzero and no larger than the selected
   slot capacity before copying.
4. Bind all records to one handle and one 20-byte capture/enrollment ID.
5. Retain exactly three feature records; use the fourth live record with the
   same real `cv_fingerprint_create_template` function resolved from the
   verified local-scope target.
6. Provide a bounded output buffer and let native command `0x6f` fill the
   template and length.
7. Stop before Linux state 2 unless all invariants hold:
   - four valid nonempty feature records;
   - command `0x6f` native status `0x00`;
   - returned template length nonzero and within capacity;
   - template bytes changed within bounds;
   - a native, understood commit token and matching commit state exist.
8. On any failure, zero and release repository-owned feature/template
   buffers, cancel once, discard through the appropriate known path, and
   never synthesize status zero.

Required logs are selector evidence, session/capture ID identity, feature
index and length (not biometric payload bytes), `0x6f` start/result, template
length, completion source, token provenance, every invariant result, and
cleanup. Raw biometric feature or template bytes should not be written to
ordinary logs.

Because the selected Windows commit is not generic `0x6e`, a first
experiment should end after proving template creation and cleanup. A later
commit experiment requires separate static reconstruction and explicit
authorization.

## Evidence classification

### Proven on hardware

- Bounded second `0x6c` after each `0x59` returned `0x89`.
- The corresponding `0x8a` recovery succeeded.
- Accepted progress exceeded the advertised 10 stages.
- Completion remained `0x00`.
- The 20-byte enrollment output remained zero.
- State 2 and commit were not reached.

### Proven by static analysis

- The Linux stage count ten is class metadata, not firmware data.
- The Linux accepted counter has no ten-stage completion cap.
- The A21 selected path buffers three features and uses a fourth live feature.
- It calls template-create command `0x6f`, then writes completion one and a
  token only on native success.
- Its commit and discard paths are separately selected and differ from
  generic `0x6e`/`0x6d`.
- The Linux target contains the `0x6f` primitive but not the integrated
  selected update/commit coordinator.
- Linux `output_value_out = 0x00007fc3` on the observed nonzero paths is
  uninitialized caller stack storage.

### Strong inference

- The repeated Linux three-sample boundary is caused by running the generic
  `0x6c` path on hardware for which A21 intended the selected host path.
- Historical `0x8d`/`0x24` commit errors may result from entering generic
  commit without selected-path template state.

### Still unproven

- Which branch A21 selects on this Latitude 7390 at Windows runtime.
- The exact Linux API needed to retrieve the same current feature bytes.
- The complete selected commit payload/operation semantics.
- Correct completion and template generation on this device under Linux.
- Template persistence, verification, fprintd, GNOME, or PAM behavior.
