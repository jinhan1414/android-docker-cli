## Context
`android-docker-cli` runs OCI/Docker images on Android (Termux) using `proot`, without a Docker engine. This means:

- There is no real container runtime; execution happens as the Termux app user.
- Many upstream images expect Docker defaults: PID 1 starts as root, may `chown` bind mounts, then drop privileges.

The reported failure for `registry.cn-hangzhou.aliyuncs.com/hass-panel/hass-panel:latest` shows both patterns:

- `chown ... Operation not permitted`
- `Can't drop privilege as nonroot user` (typical when `supervisord` is started as non-root but configured to run managed programs under a different user).

## Goals / Non-Goals
- Goals:
  - Provide a supported way to run containers with a root-like identity in Android/Termux proot runs.
  - Avoid requiring users to know or pass special flags for common "needs root at startup" images.
  - Ensure the behavior is consistent across foreground, detached, and restart/start flows.
- Non-Goals:
  - Provide real root privileges on the Android host (this is not possible via proot).
  - Implement a full Docker `--user` matrix (arbitrary uid/gid mapping) unless required later.
  - Automatically detect "needs root" images heuristically (avoid fragile detection).

## Decisions
### Decision: Enable proot fake-root by default on Android/Termux
When `_is_android_environment()` is true, include proot fake-root behavior (commonly `proot -0 ...`) by default.

Rationale:
- Matches Docker defaults (root startup) more closely, which is what many images assume.
- Removes a UX footgun: users should not need to learn about privilege emulation to run common images.

### Decision: Provide an internal escape hatch via environment variable
Support disabling fake-root via an environment variable (for example `ANDROID_DOCKER_FAKE_ROOT=0`) so advanced users can troubleshoot edge cases without introducing a prominent new CLI surface area.

Rationale:
- Keeps the default experience simple while still allowing a way out if an image behaves unexpectedly.

### Decision: Persist fake-root setting in container metadata
Persist the run mode as part of stored `run_args` so `docker start` / `docker restart` reuses the same behavior.

Rationale:
- Restart semantics should match the original run configuration.

## Alternatives Considered
- Add output-based hints (detect `Can't drop privilege...` and suggest fake-root):
  - Pros: better UX.
  - Cons: requires reliable log capture in interactive mode; adds complexity.
- Implement Docker-like `--user`:
  - Pros: more flexible.
  - Cons: more surface area; unclear mapping to proot; not needed to resolve current issue.

## Risks / Trade-offs
- Some images may behave differently when they believe they are root (for example, attempting operations that still fail on the Android host due to kernel-enforced permissions).
  - Mitigation: provide an escape hatch to disable fake-root; keep the rest of the Android hardening unchanged.
- proot fake-root behavior can be proot-version dependent.
  - Mitigation: treat the proot flag as the contract; add tests that verify command construction, and document minimum expectations.

## Migration Plan
- No migration required.
- Documentation/release notes: describe the compatibility improvement without requiring users to take action.

## Open Questions
- Do we need a user-facing CLI flag later if the environment-variable escape hatch is not sufficient for support/debug workflows?
