# Change: Add Android /etc/hosts bind for localhost resolution

## Why
Android/Termux runs can fail with `getaddrinfo ENOTFOUND localhost` because images expect a localhost entry in `/etc/hosts`. We cannot control the images, so the tool should supply a safe default for Android.

## What Changes
- Generate a host-side `/etc/hosts` file for Android runs, seeded from the rootfs file when present and ensuring localhost entries.
- Bind the generated file into the container at `/etc/hosts` during Android runs.

## Impact
- Affected specs: hosts-resolution (new)
- Affected code: android_docker/proot_runner.py, tests/test_android_permissions.py
