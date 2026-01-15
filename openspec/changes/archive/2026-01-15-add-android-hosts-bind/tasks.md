## 1. Implementation
- [x] 1.1 Add Android hosts bind generation in `android_docker/proot_runner.py` (create host-side file, merge rootfs `/etc/hosts`, ensure localhost entries, add bind mount; prerequisite for tests).
- [x] 1.2 Add unit tests in `tests/test_android_permissions.py` for hosts file generation/binding (depends on 1.1).
- [x] 1.3 Run `pytest tests/test_android_permissions.py -k hosts` (or full suite) to validate.
