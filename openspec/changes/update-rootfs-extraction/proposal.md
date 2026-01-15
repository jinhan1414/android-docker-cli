# Change: Update rootfs extraction to preserve executable permissions

## Why
Rootfs extraction on Android currently normalizes file modes to 0644, which strips executable bits. This causes extracted images (for example, nginx:alpine) to fail at runtime with errors like "/bin/busybox" not executable.

## What Changes
- Preserve executable bits when normalizing file permissions during Android layer extraction.
- Add tests that verify executable files remain runnable after Python tar extraction on Android.
- Keep non-Android extraction behavior unchanged.

## Impact
- Affected specs: rootfs-extraction (new)
- Affected code: android_docker/create_rootfs_tar.py, tests/test_android_permissions.py
