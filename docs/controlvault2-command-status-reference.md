# ControlVault2 command and status reference

## Research scope

This repository contains independently derived interoperability research for
Linux support of lawfully owned Broadcom ControlVault2 hardware.

Command names marked as inferred are not official Broadcom terminology.

No proprietary binaries, firmware, cryptographic keys, raw fingerprint
features, biometric templates, personal identifiers, or authentication
credentials are included.

## Interpretation rules

“Export pairing” means a short wrapper in the analyzed Broadcom library passes
the listed constant to its common CV transport routine. It establishes the
code-to-wrapper relationship but does not make the descriptive name official
vendor terminology.

“Hardware” records only command/status order and aggregate state changes. Raw
USB payloads and biometric data are not included.

## Commands

| Code | Observed behavior | Evidence type | Confidence | Terminology | Known next transition |
|---|---|---|---|---|---|
| `0x20` | Used by exported `cv_fingerprint_enroll` wrapper. | Linux export pairing | High for pairing | Inferred: fingerprint enroll operation | Function-dependent completion/status |
| `0x30` | Used by exported `cv_fingerprint_configure` wrapper. | Linux export pairing | High for pairing | Inferred: fingerprint configuration | Returns native status |
| `0x39` | Queries USH version data; request/reply completed on `0a5c:5833`. | Linux export pairing and hardware | High | Inferred from `cv_get_ush_ver` export | Version response, then probe classification |
| `0x41` | Used by exported `cv_enable_fingerprint` wrapper. | Linux export pairing | High for pairing | Inferred: enable fingerprint function | Returns native status |
| `0x5c` | Used by exported `cv_fingerprint_capture` wrapper. | Linux export pairing | High for pairing | Inferred: synchronous/native capture | Returns capture-dependent outputs |
| `0x5d` | Used by exported `cv_fingerprint_reset` wrapper. | Linux export pairing | High for pairing | Inferred: fingerprint reset operation | Returns native status |
| `0x66` | Starts an enrollment capture in the analyzed TOD path. | Linux CFG and hardware | High | Inferred: CaptureStart | Interrupt completion, then update |
| `0x68` | Used by exported `cv_fingerprint_capture_cancel` wrapper. | Linux export pairing and cleanup CFG | High | Inferred: CaptureCancel | Cleanup or discard |
| `0x69` | Used by exported `cv_fingerprint_capture_get_result` wrapper. | Linux export pairing | High for pairing | Inferred: capture-result retrieval | Returns capture-dependent outputs |
| `0x6a` | Used by exported `cv_fingerprint_create_feature_set` wrapper. | Linux export pairing | High for pairing | Inferred: create feature set | Returns native status/output |
| `0x6b` | Used by exported `cv_fingerprint_commit_feature_set` wrapper. | Linux export pairing | High for pairing | Inferred: commit feature set | Returns native status |
| `0x6c` | Generic Linux UpdateEnrollment operation. | Linux CFG and hardware | High | Inferred: UpdateEnrollment | Status/completion dispatch |
| `0x6d` | Generic Linux enrollment discard operation. | Linux CFG | High | Inferred: DiscardEnrollment | Fatal/cancellation cleanup |
| `0x6e` | Generic Linux enrollment commit operation. | Linux CFG | High | Inferred: CommitEnrollment | Commit result; not reached on tested `5833` |
| `0x6f` | Four-feature template primitive in Linux and Windows analysis. | Linux/Windows CFG | High | Inferred: CreateTemplate | On selected Windows success, retained template and completion |
| `0x70` | Used by exported `cv_fingerprint_enroll_dup_check` wrapper. | Linux export pairing | High for pairing | Inferred: enrollment duplicate check | Returns native status |
| `0x8a` | Prepares/re-arms the next enrollment capture. | Windows CFG and hardware retry order | High for observed transition | **Inferred:** enrollment capture re-arm/preparation command | Successful call is followed by `0x66` |

`0x8a` is not called “rollback”, “reset”, or “acknowledge” here because those
names are not established by the available evidence.

## Statuses

| Code | Observed behavior | Evidence type | Confidence | Terminology | Known next transition |
|---|---|---|---|---|---|
| `0x00` | Native call success. During generic Linux update, completion zero is converted to synthetic `0x8f`; completion one can reach state 2. | Linux CFG and mock tests | High | Generic success; not necessarily enrollment complete | Depends on completion output |
| `0x59` | Appears after groups of three accepted samples on the tested device. One bounded repeated `0x6c` returned `0x89`; generic Linux otherwise treats it as fatal. | Hardware and Linux/Windows static analysis | High for behavior, low for semantic meaning | Mode/firmware-path-dependent special state; exact name unknown | Diagnostic path: one repeated `0x6c`; production transition unresolved |
| `0x89` | Windows maps it to bad-capture/poor-quality framework results. On tested hardware, one `0x8a` followed by normal retry capture succeeds. | Windows CFG and hardware | High for behavior | Firmware semantic name not asserted | `0x8a → 0x66` |
| `0x8f` | Synthesized by the Linux host wrapper when native update succeeds but completion is zero. It is not a raw firmware status in this path. | Linux CFG | High | Synthetic host “more enrollment progress” state | Increment host counter and issue next `0x66` |
| `0xa4` | Has a dedicated retry branch in the unmodified Linux outer callback. | Linux CFG and regression tests | High for branch, low for semantic meaning | Exact semantic name unknown | Preserve state 1 and issue next `0x66` |

## Scope limits

The table documents code associations and observed transitions, not a complete
vendor protocol specification. Enrollment completion, matched BCM5880 commit,
template persistence, and verification remain unproven.
