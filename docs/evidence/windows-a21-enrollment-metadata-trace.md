# Windows A21 enrollment metadata trace

This is the next reference experiment after the USB-header-only Windows
enrollment capture.  It observes the exact Dell/Broadcom A21 x64 biometric
stack at function boundaries so that a successful Windows enrollment can be
compared with the Linux path without recording fingerprint or template bytes.

No runtime result is claimed in this document yet.  It describes the pinned,
reviewed tracer and the evidence fields that a future Windows VM run will
produce.

## Pinned artifacts and hook site

The runner accepts only these loaded Windows 10 x64 files from Dell package
`N23KC`, version `4.12.5.8 A21`:

| Loaded module | SHA-256 |
|---|---|
| `bipdll.dll` | `30c556a9b542d0fcf29a6822b3bb81fe23ce2917b403b3f25af9384e0e31e524` |
| `BrcmEngineAdapter.dll` | `622b1a12566cb313cde264869ca5a4b410e3d5b2b604f5dd628c4a6b709b19ae` |
| `BrcmSensorAdapter.dll` | `dfb30d81de42e726477b103412fba2c88abd9b675ead7141f25063a3ac8d4e6c` |

The internal route observation is at `bipdll.dll` RVA `0x2d249`, the
`test al,al` immediately after the A21 `is5880` call in the
UpdateEnrollment dispatcher.  The exact surrounding signature occurs once
at file offset `0x2c642`.  `tools/audit_windows_a21_update.py` now validates
that anchor before the RVA is used as evidence.

The tracer also resolves the following exports by name from the same pinned
`bipdll.dll`:

- capture start and capture-mode selection;
- UpdateEnrollment;
- CSS and raw commit-enrollment/commit-feature-set calls; and
- CSS and raw discard-enrollment calls.

This identifies whether the runtime selected the generic command-`0x6c` or
BCM5880 host-template branch and which named operation produced the two
completion-stage calls seen in the successful USB trace.

## Privacy and mutation boundary

`tools/windows_a21_enrollment_trace.js` deliberately has no bulk-memory,
string-reading, hex-dump, memory-scan, memory-write, or Frida message-send
primitive.  It reads at most the known scalar fields and twenty individual
bytes solely to reduce a buffer to one of these labels:

```text
zero  nonzero  null  unreadable
```

It emits only:

- call order and symbol name;
- return status;
- zero/nonzero classifications;
- whether two pointers are the same, without printing either address;
- whether two twenty-byte regions are equal, without retaining or printing
  either region; and
- the generic-versus-BCM5880 route decision.

It never prints or retains capture IDs, fingerprint samples, feature sets,
templates, tokens, user identifiers, device serials, or pointer addresses.
Static tests reject the payload-reading/writing APIs listed above.

The tracer does not patch a DLL on disk, write process memory, change the
registry, restart a service, install a driver, or issue a firmware command.
Frida attachment is nevertheless process instrumentation: a Frida or target
process failure can interrupt Windows Biometric Service for that VM session.
A service or VM restart is the recovery action.  Run this only after saving
other work in the VM.

## Windows VM procedure

Prerequisites:

1. The exact A21 stack above is installed and the biometric device is healthy.
2. For the previously tested QEMU pass-through setup,
   `suppress-remote-wake=false` remains required for this legacy lower-filter
   stack.
3. Matching x64 Frida CLI tools are already installed in the Windows VM.
4. An elevated Windows PowerShell is open in a checkout of this repository.

Open Windows Hello fingerprint settings and touch the sensor once so the
adapter pipeline is loaded.  Then run:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\tools\run_windows_a21_enrollment_trace.ps1 -ConfirmPrivacySafeTrace
```

The runner searches for a process containing all three pinned A21 modules,
then hashes the loaded module files before attaching.  If automatic discovery
finds more than one candidate, pass the displayed PID explicitly:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\tools\run_windows_a21_enrollment_trace.ps1 -ConfirmPrivacySafeTrace -TargetProcessId 1234
```

Wait for:

```text
cv2win event=trace-ready action=start_Windows_Hello_enrollment
```

Perform exactly one enrollment attempt, then press `Ctrl+C` after Windows
reports success or failure.  The metadata-only log is written under
`test-results/`.  Use separate trace processes for a successful control and
a failed control; do not concatenate multiple attempts into one session.

## Evidence interpretation

The most important fields are:

| Event/field | Question answered |
|---|---|
| `capture-start-leave output20_class` | Did A21 produce a nonzero twenty-byte capture/enrollment value? |
| `update-enter input_matches_capture_start` | Did UpdateEnrollment receive the exact CaptureStart output? |
| `update-route route` | Did this live `0a5c:5833` session use generic `0x6c` or the BCM5880 host-template helper? |
| `update-leave completion_post` | On which accepted update did the completion byte become nonzero? |
| `update-leave output20_post/output4_post` | Which output classes changed at that boundary? |
| `commit-enter/leave symbol` | Which CSS/raw commit function actually followed the updates? |
| `discard-enter/leave symbol` | Which discard path closed a failed attempt? |

Zero/nonzero or equality evidence does not establish the semantic contents of
an opaque field.  A nonzero output must not be copied into the Linux driver
until its ownership, length, and downstream consumer are separately proven.
