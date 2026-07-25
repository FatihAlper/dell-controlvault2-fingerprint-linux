#!/usr/bin/env bash
# Build a repository-local libfprint-tod loader and the staged probe harness.
# No package manager, system prefix, service, PAM, or udev state is modified.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL="$REPO/.local-test"
VENV="$REPO/.venv"
TOD_SOURCE="$LOCAL/libfprint-tod"
TOD_BUILD="$LOCAL/libfprint-build"
TOD_TAG="v1.95.2+tod1"
TOD_COMMIT="461d57c64cabea5320438388a16aa4b41a9a90cc"
TOD_URL="https://gitlab.freedesktop.org/3v1n0/libfprint.git"
GLIB_URL="https://gitlab.gnome.org/GNOME/glib.git"

for command in gcc git pkg-config python3 sha256sum; do
    if ! command -v "$command" >/dev/null; then
        echo "missing build command: $command" >&2
        exit 1
    fi
done

for package in glib-2.0 gio-unix-2.0 gobject-2.0 gusb gudev-1.0 openssl; do
    if ! pkg-config --exists "$package"; then
        echo "missing build dependency: $package" >&2
        echo "this script will not install system packages" >&2
        exit 1
    fi
done

if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check \
    -r "$REPO/requirements-test.txt"
export PATH="$VENV/bin:$PATH"

mkdir -p "$LOCAL"
if [[ ! -d "$TOD_SOURCE/.git" ]]; then
    git clone --depth 1 --branch "$TOD_TAG" "$TOD_URL" "$TOD_SOURCE"
fi
ACTUAL_TOD_COMMIT="$(git -C "$TOD_SOURCE" rev-parse HEAD)"
if [[ "$ACTUAL_TOD_COMMIT" != "$TOD_COMMIT" ]]; then
    echo "unexpected libfprint-tod source commit" >&2
    echo "expected: $TOD_COMMIT" >&2
    echo "actual:   $ACTUAL_TOD_COMMIT" >&2
    exit 1
fi

PKG_OVERRIDE=""
if ! command -v glib-mkenums >/dev/null ||
   ! command -v glib-genmarshal >/dev/null; then
    GLIB_VERSION="$(pkg-config --modversion glib-2.0)"
    GLIB_SOURCE="$LOCAL/glib-$GLIB_VERSION"
    GLIB_BUILD="$LOCAL/glib-build"
    GLIB_PREFIX="$LOCAL/glib-prefix"
    GLIB_TOOLS="$GLIB_BUILD/gobject"
    PKG_OVERRIDE="$LOCAL/pkgconfig"

    if [[ ! -d "$GLIB_SOURCE/.git" ]]; then
        git clone --depth 1 --branch "$GLIB_VERSION" "$GLIB_URL" "$GLIB_SOURCE"
    fi
    if [[ "$(git -C "$GLIB_SOURCE" describe --tags --exact-match)" != "$GLIB_VERSION" ]]; then
        echo "local GLib source is not the installed version $GLIB_VERSION" >&2
        exit 1
    fi

    if [[ ! -x "$GLIB_TOOLS/glib-mkenums" ||
          ! -x "$GLIB_TOOLS/glib-genmarshal" ]]; then
        meson setup "$GLIB_BUILD" "$GLIB_SOURCE" \
            --prefix="$GLIB_PREFIX" \
            -Dtests=false \
            -Dinstalled_tests=false \
            -Ddocumentation=false \
            -Dman-pages=disabled \
            -Ddtrace=disabled \
            -Dsystemtap=disabled \
            -Dsysprof=disabled
    fi

    mkdir -p "$PKG_OVERRIDE"
    GLIB_PC_DIR="$(pkg-config --variable=pcfiledir glib-2.0)"
    cp "$GLIB_PC_DIR/glib-2.0.pc" "$PKG_OVERRIDE/glib-2.0.pc"
    sed -i "s|^bindir=.*|bindir=$GLIB_TOOLS|" \
        "$PKG_OVERRIDE/glib-2.0.pc"
fi

if [[ -n "$PKG_OVERRIDE" ]]; then
    export PKG_CONFIG_PATH="$PKG_OVERRIDE"
fi

MESON_ARGS=(
    "--prefix=$LOCAL/prefix"
    "-Ddrivers=virtual_device"
    "-Dtod=true"
    "-Dintrospection=false"
    "-Ddoc=false"
    "-Dinstalled-tests=false"
    "-Dudev_rules=disabled"
    "-Dudev_hwdb=disabled"
)
if [[ -f "$TOD_BUILD/build.ninja" ]]; then
    meson setup --reconfigure "$TOD_BUILD" "$TOD_SOURCE" "${MESON_ARGS[@]}"
else
    meson setup "$TOD_BUILD" "$TOD_SOURCE" "${MESON_ARGS[@]}"
fi

ninja -C "$TOD_BUILD" \
    libfprint/tod/libfprint-2-tod.so.1 \
    examples/tod-inspector

"$REPO/build_from_upstream.sh" --target-pid 5833 --patch-set probe
mkdir -p "$LOCAL/tod-drivers" "$LOCAL/bin"
cp "$REPO/prebuilt/libfprint-2-tod-1-broadcom-5833.probe.so" \
    "$LOCAL/tod-drivers/libfprint-2-tod-1-broadcom-5833.probe.so"

if [[ -n "$PKG_OVERRIDE" ]]; then
    export PKG_CONFIG_PATH="$TOD_BUILD/meson-uninstalled:$PKG_OVERRIDE"
else
    export PKG_CONFIG_PATH="$TOD_BUILD/meson-uninstalled"
fi
# pkg-config emits a conventional whitespace-separated compiler flag list.
# shellcheck disable=SC2046
gcc -Wall -Wextra -Werror "$REPO/tools/cv_tod_probe.c" \
    -o "$LOCAL/bin/cv_tod_probe" \
    $(pkg-config --cflags --libs libfprint-2-uninstalled)

echo "Repository-local TOD test environment is ready."
echo "Run: tools/run_local_tod_test.sh --stage load|probe|open"
