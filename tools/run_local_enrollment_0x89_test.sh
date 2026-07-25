#!/usr/bin/env bash
# Explicit opt-in runner for a real repository-local enrollment experiment.
# It installs nothing and records logical CV command evidence from the
# interposer.  This is not a USB bus trace.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$REPO/.local-test"
EXPERIMENT="$LOCAL/enrollment-0x89"
TARGET="$LOCAL/tod-drivers/libfprint-2-tod-1-broadcom-5833.probe.so"
PRELOAD="$EXPERIMENT/libcv2-enrollment-0x89-rearm.so"
HARNESS="$EXPERIMENT/cv_tod_enrollment_experiment"
CONFIRMED=no
CHILD_PID=""

usage() {
    cat <<'EOF'
Usage:
  tools/run_local_enrollment_0x89_test.sh --confirm-real-enrollment

WARNING: this exercises real enrollment. If all stages succeed, the
ControlVault driver may commit a fingerprint template inside the device.
Nothing is installed and no PAM, GNOME, udev, systemd, or system libfprint
configuration is changed.
EOF
}

while (($#)); do
    case "$1" in
        --confirm-real-enrollment)
            CONFIRMED=yes
            shift
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

if [[ "$CONFIRMED" != yes ]]; then
    usage >&2
    echo "refusing to touch hardware without the explicit confirmation flag" >&2
    exit 2
fi

"$REPO/tools/build_enrollment_0x89_experiment.sh"
for required in "$TARGET" "$PRELOAD" "$HARNESS"; do
    if [[ ! -e "$required" ]]; then
        echo "repository-local test prerequisite missing: $required" >&2
        exit 1
    fi
done

TARGET_CANONICAL="$(realpath -e "$TARGET")"

VALIDATION="$(
    python3 "$REPO/tools/enrollment_0x89_target.py" \
        "$TARGET" --preload "$PRELOAD"
)"
EXPERIMENT_PRELOAD="$(
    sed -n 's/^validated_LD_PRELOAD=//p' <<<"$VALIDATION"
)"
if [[ -z "$EXPERIMENT_PRELOAD" ]]; then
    echo "validator did not produce an LD_PRELOAD value" >&2
    exit 1
fi

export LD_LIBRARY_PATH="$LOCAL/libfprint-build/libfprint/tod:$LOCAL/libfprint-build/libfprint"
export FP_TOD_DRIVERS_DIR="$LOCAL/tod-drivers"
export FP_DRIVERS_ALLOWLIST="broadcom"
export G_MESSAGES_DEBUG="all"
export CV2_0X89_TARGET_PATH="$TARGET_CANONICAL"

mkdir -p "$REPO/test-results"
STAMP="$(date --iso-8601=seconds | tr ':' '-')"
LOG="$REPO/test-results/enrollment-0x59-single-update-retry-$STAMP.log"

cleanup() {
    local signal="${1:-TERM}"
    if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
        echo "forwarding $signal to enrollment harness" | tee -a "$LOG"
        kill "-$signal" "$CHILD_PID" 2>/dev/null || true
        wait "$CHILD_PID" || true
    fi
}
trap 'cleanup INT; exit 130' INT
trap 'cleanup TERM; exit 143' TERM

{
    echo "evidence_timestamp=$(date --iso-8601=seconds)"
    echo "$VALIDATION"
    echo "evidence_scope=repository-local logical command logging; not USBPcap"
    echo "experiment=bounded single repeated UpdateEnrollment after native 0x59"
    echo "retry_limit=one additional 0x6C call per intercepted invocation"
    echo "interposer_target=$CV2_0X89_TARGET_PATH"
    echo "warning=successful enrollment may commit a device template"
} | tee "$LOG"

set +e
LD_PRELOAD="$EXPERIMENT_PRELOAD" \
    "$HARNESS" > >(tee -a "$LOG") 2>&1 &
CHILD_PID=$!
wait "$CHILD_PID"
STATUS=$?
CHILD_PID=""
set -e

echo "harness_exit_status=$STATUS" | tee -a "$LOG"
echo "evidence_file=$LOG"
exit "$STATUS"
