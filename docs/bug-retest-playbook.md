# Bug Retest Playbook

This document defines the default mechanism to reproduce and verify Android/Termux-related bugs for this repository.

## Scope

- Project: `android-docker-cli`
- Goal: reproducible bug replay and fix regression verification in CI
- Constraint: CI execution must remain non-root to mirror Android user-space limits

## Workflow

1. Normalize bug input
- Required: bug summary, trigger command/compose, expected failure signature, affected version or commit.
- Optional: target image, environment variables, expected exit behavior.

2. Build automated repro
- Prefer deterministic script/test with pass/fail criteria.
- For deploy-path issues, use `scripts/repro_issue4_deploy.sh` pattern:
  - execute compose/docker flow
  - capture logs
  - grep target error signature
  - return explicit status code

3. Trigger CI repro
- Workflow: `Bug Retest (Android-Constrained Simulation)` (`.github/workflows/bug-retest.yml`)
- Inputs:
  - `bug_id`: label for traceability
  - `target_ref`: version/branch/tag/SHA to retest
  - `scope`: choose `deploy-repro` for deploy flow issues
  - `deploy_expect`:
    - `reproduced` for baseline confirmation
    - `fixed` after patch
  - `fake_root`: usually `1`
- For `deploy-repro`, CI must execute the README installation path first (installer command), then run installed `docker`/`docker-compose` commands for replay.
- For `deploy-repro`, run `docker-compose up -d`, collect container logs plus `docker inspect`/`docker ps` snapshots for runtime-state evidence, then always run `docker-compose down` for cleanup.

4. Implement fix
- Keep fix minimal and scoped to the failing behavior.
- Preserve existing Android constraints and non-root assumptions.

5. Verify fix
- Re-run same workflow with same bug input but `deploy_expect=fixed`.
- Validate job conclusion and inspect uploaded artifacts/log tails.

## CI Notes

- Deploy repro has timeout protection at both script and workflow step level to avoid indefinite blocking.
- Deploy repro should avoid direct `python -m android_docker...` execution; prefer installed CLI wrappers to match user behavior.
- Artifacts are uploaded on `always()` for postmortem.
- If repro fails due to environment variance (network, remote image changes), capture and report the exact failing phase before changing code.

## Handoff Template

When reporting back after a retest run, include:

1. Run URL
2. Commit SHA
3. Inputs used (`scope`, `deploy_expect`, `fake_root`)
4. Result (`reproduced` / `fixed` / `inconclusive`)
5. Key log evidence (short excerpt)
6. Next action

## Remember Action Protocol

Use this protocol whenever the user asks to "remember" a workflow or rule.

1. Capture
- Identify what must be remembered: trigger conditions, required inputs, success criteria, and constraints.

2. Persist
- Write a concise summary into `AGENTS.md`.
- Write/extend detailed operational steps in this document (or a sibling doc under `docs/` if scope is different).

3. Cross-link
- Ensure `AGENTS.md` references the detailed doc path for progressive disclosure.

4. Verify
- Confirm files are updated and paths are correct.
- Prefer including line references in the handoff response.

5. Apply by default
- On future bug requests, execute the persisted workflow first, then adapt minimally per case.
