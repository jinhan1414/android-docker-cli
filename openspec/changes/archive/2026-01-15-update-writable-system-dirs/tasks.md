## 1. Implementation
- [x] 1.1 Add seeding logic for writable system directories in android_docker/proot_runner.py (mirror existing rootfs directory structure into host writable dirs, do not overwrite existing contents).
- [x] 1.2 Add unit tests for seeding behavior in tests/test_android_permissions.py (create a rootfs with nested directories and verify the host writable dirs include them).
- [x] 1.3 Review integration coverage; no updates needed for nginx startup in this change.
- [x] 1.4 Run pytest (targeted tests and/or full suite) to validate the change.
