#!/usr/bin/env bash
# Run one explicitly selected TOD bring-up stage from the repository-local
# environment produced by prepare_local_tod_test.sh.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$REPO/.local-test"
STAGE=""
TIMEOUT_SECONDS=20

usage() {
    cat <<'EOF'
Usage: tools/run_local_tod_test.sh --stage load|probe|open

  load   Load the plugin and print its runtime ID table; no USB enumeration.
  probe  Enumerate USB and require successful Broadcom driver probe.
  open   Probe, then open and close; no enroll/verify/identify/list operation.
EOF
}

while (($#)); do
    case "$1" in
        --stage)
            STAGE="${2:?--stage requires a value}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "$STAGE" in
    load|probe|open) ;;
    *)
        usage >&2
        exit 2
        ;;
esac

TOD_LIBRARY="$LOCAL/libfprint-build/libfprint/tod/libfprint-2-tod.so.1"
PLUGIN="$LOCAL/tod-drivers/libfprint-2-tod-1-broadcom-5833.probe.so"
HARNESS="$LOCAL/bin/cv_tod_probe"
INSPECTOR="$LOCAL/libfprint-build/examples/tod-inspector"
for required in "$TOD_LIBRARY" "$PLUGIN" "$HARNESS" "$INSPECTOR"; do
    if [[ ! -e "$required" ]]; then
        echo "local test environment is incomplete: $required" >&2
        echo "run tools/prepare_local_tod_test.sh first" >&2
        exit 1
    fi
done

export LD_LIBRARY_PATH="$LOCAL/libfprint-build/libfprint/tod:$LOCAL/libfprint-build/libfprint"
export FP_TOD_DRIVERS_DIR="$LOCAL/tod-drivers"
export FP_DRIVERS_ALLOWLIST="broadcom"
export G_MESSAGES_DEBUG="all"

mkdir -p "$REPO/test-results"
LOG="$REPO/test-results/5833-tod-$STAGE.log"

set -o pipefail
if [[ "$STAGE" == "load" ]]; then
    timeout --signal=TERM "$TIMEOUT_SECONDS"s "$INSPECTOR" 2>&1 | tee "$LOG"
else
    timeout --signal=TERM "$TIMEOUT_SECONDS"s \
        "$HARNESS" --stage "$STAGE" 2>&1 | tee "$LOG"
fi
