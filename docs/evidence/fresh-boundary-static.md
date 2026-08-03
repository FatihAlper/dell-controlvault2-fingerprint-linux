# Evidence for the fresh-sample enrollment boundary policy

## Scope

This record covers repository-local source, mock tests, and one bounded
hardware run on the tested Latitude 7390. The run did not install a driver,
write firmware, reach template commit, or expose biometric payload bytes.

The policy is selected explicitly:

```text
CV2_ENROLLMENT_UPDATE_POLICY=fresh-stop-before-commit
```

The historical `legacy-repeat` behavior remains the default so existing
evidence remains reproducible.

## Control flow

The interposer continues to wrap only
`cv_fingerprint_update_enrollment`. Under the fresh-boundary policy:

```text
native update status 0x59
  -> log redacted output metadata
  -> return native 0x59 unchanged
  -> unchanged outer callback performs fatal cleanup/discard
  -> no same-update replay

native update status 0x00, completion 0
  -> return native 0x00 unchanged
  -> unchanged state machine requests the next fresh capture

native update status 0x00, completion nonzero
  -> log the native completion boundary
  -> return experiment-fatal status before state 2
  -> unchanged outer callback performs one cancel and one discard
  -> generic commit is not entered
```

A null completion pointer on native success is also blocked because the
experiment cannot validate the commit boundary in that case. Native `0x89`
retains the already tested `0x8a` re-arm behavior.

## Mock evidence

Repository-local tests prove:

- an invalid policy fails resolver readiness before an update command;
- native `0x59` causes exactly one real `0x6c` and one existing cleanup;
- native success with completion zero passes unchanged;
- native success with completion one is converted to experiment-fatal before
  state 2 and causes exactly one existing cancel/discard;
- capture, commit, verify, cancel, and discard functions are not interposed;
- the target DSO remains hash-validated and is not modified.

The full suite currently reports 46 passing tests.

## Hardware result

The first hardware run was limited to one attempt. Its privacy-safe command
sequence was:

```text
0x8a -> 0x66 -> 0x6c = 0x89
     -> 0x8a -> 0x66 -> 0x6c = 0x00, completion 0
              -> 0x66 -> wait
```

The second update produced accepted progress `1/10`. The unchanged state
machine then issued a genuinely fresh `0x66` capture within milliseconds, so
the policy did establish a fresh-sample boundary. It did not issue `0x8a`
between the accepted incomplete update and that next capture. Four physical
lift-and-touch attempts produced no further completed capture or `0x6c`.

Clean cancellation was requested after the bounded wait. The trace contains
one `0x68` cancellation request and no `0x6d`, `0x6e`, or `0x6f`. The
proprietary call did not return from cancellation, so the repository-local
process was terminated. The USB capture retained 760 packets with zero drops,
and the device remained enumerated as `0a5c:5833` afterward.

This result narrows the next hypothesis: an accepted update with completion
zero may require `0x8a` re-arm before the next native `0x66`, matching the
three between-capture `0x8a` operations in the successful four-update Windows
control. That behavior is not implemented by the current policy and requires
a separately mock-tested, one-attempt experiment.
