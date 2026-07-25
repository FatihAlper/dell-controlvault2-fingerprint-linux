# Arch/CachyOS packaging notes

The runtime TOD loader uses the Arch library directory:

```text
/usr/lib/libfprint-2/tod-1/
```

and udev rules belong under:

```text
/usr/lib/udev/rules.d/
```

`stage.sh` mirrors that layout under `stage/arch/` inside this repository. It
does not install anything, run `pacman`, reload udev, or modify authentication.

For the current bring-up scope, stage only the `5833.probe` artifact. It
contains patches 1-3 and intentionally excludes enrollment and verification
patches:

```sh
./build_from_upstream.sh --target-pid 5833 --patch-set probe
packaging/arch/stage.sh
```

The staged plugin has an external ABI dependency on `libfprint-2-tod.so.1`.
Stock Arch `libfprint` does not provide that SONAME. Do not replace the system
fingerprint stack during probe development; use the repository-local test
environment documented in the main README instead.
