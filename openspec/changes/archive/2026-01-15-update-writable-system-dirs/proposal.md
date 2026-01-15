# Change: Seed Android writable system directories from rootfs

## Why
Android writable system directory binds replace image paths like /var/log and /var/cache with empty host directories, which drops required subdirectories (for example /var/log/nginx and /var/cache/nginx). This causes images like nginx to fail at startup in Termux.

## What Changes
- Seed each writable system directory bind with the existing directory structure from the rootfs before binding.
- Only seed when the host writable directory is new or empty to avoid overwriting runtime data.
- Add tests covering seeded directory structure for writable directories on Android.

## Impact
- Affected specs: writable-system-dirs (new)
- Affected code: android_docker/proot_runner.py, tests/test_android_permissions.py, tests/test_android_integration.py (if needed)
