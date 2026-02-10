# Change: Enable Fake-Root By Default For Android/Termux Runs

## Why
Some images assume the container starts as root, performs `chown` on bind-mounted directories, and then drops privileges (for example via `supervisord`). In Android/Termux proot runs, processes currently execute as the host user, which commonly triggers errors like:

- `chown: ... Operation not permitted`
- `Error: Can't drop privilege as nonroot user`

The tool cannot change third-party images, so it needs a way to emulate a root-like runtime identity inside proot.

## What Changes
- Automatically execute containers under proot "fake root" (uid=0) semantics (via proot flag) when running in Android/Termux, so images can `chown` and drop privileges as they would under Docker, without requiring users to pass additional flags.
- Provide an internal escape hatch to disable fake-root for troubleshooting (environment variable based), without making it part of the primary user-facing CLI.
- Ensure the effective fake-root setting is consistently applied across:
  - foreground runs (android_docker/docker_cli.py -> ProotRunner)
  - detached runs (docker_cli spawning android_docker/proot_runner.py)
  - restart/start flows (persist effective setting in container metadata).
- Update docs/release notes to describe "improved compatibility with images that expect root startup" without requiring user action.

## Impact
- Affected specs: new `fake-root-mode`
- Affected code (implementation stage): `android_docker/proot_runner.py`, `android_docker/docker_cli.py`, and tests around command construction and container run-args persistence.
