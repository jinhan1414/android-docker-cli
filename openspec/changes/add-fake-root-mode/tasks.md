## 1. Implementation
- [x] 1.1 Enable proot fake-root by default when running in Android/Termux in `android_docker/proot_runner.py` (inject proot fake-root flag into `_build_proot_command()`).
- [x] 1.2 Add an environment-variable escape hatch to disable fake-root on Android for troubleshooting (for example `ANDROID_DOCKER_FAKE_ROOT=0`), without adding a prominent new CLI flag.
- [x] 1.3 Persist the effective fake-root setting under container `run_args` in `android_docker/docker_cli.py` so restart/start retains behavior even if the environment changes.
- [x] 1.4 Ensure detached runs pass the persisted setting from `docker_cli.py` into the spawned `python -m android_docker.proot_runner ...` invocation (via child process env).
- [x] 1.5 Add unit tests for command construction: Android default includes fake-root flag; escape hatch disables it; non-Android remains unchanged.
- [x] 1.6 Add unit tests that detached runs pass the persisted setting into the spawned process environment (so start/restart behavior is stable).
- [x] 1.7 Update release notes / docs to describe the compatibility improvement without requiring any user action or exposing internal flags.

## 2. Validation
- [x] 2.1 Run `pytest` for unit suites that do not require proot/network (ran `tests/test_android_permissions.py` and dedicated fake-root unit tests).
- [x] 2.2 Add a manual Android/Termux test case to `docs/test_plan.md` for an image known to require root startup semantics (hass-panel).
