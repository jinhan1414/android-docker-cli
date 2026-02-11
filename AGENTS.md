<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Bug Retest Memory (CI)

When the user provides a production bug report for Android/Termux behavior, follow this workflow by default:

1. Convert the report into an automated repro assertion first (script/test) before changing runtime logic.
2. Use GitHub Actions workflow `Bug Retest (Android-Constrained Simulation)` for repro and regression checks.
3. Keep non-root execution constraints in CI (Android-like limitation).
4. For deploy-path repro, use `scope=deploy-repro`:
   - Repro phase: `deploy_expect=reproduced`
   - Fix validation phase: `deploy_expect=fixed`
   - Execute via README install path and installed `docker` / `docker-compose` commands (avoid direct `python -m` for deploy replay).
5. Upload and inspect artifacts/logs for every run before concluding.

Progressive disclosure:
- Detailed playbook: `docs/bug-retest-playbook.md`

## Memory Persistence Rule

When the user says "记住" / "remember" for a project-specific workflow:

1. Persist it to repository docs in the same turn (do not keep it only in chat context).
2. Add a short rule in `AGENTS.md` and link to a detailed document under `docs/`.
3. Prefer appending to an existing playbook; create a new doc only when scope is different.
4. Report back with exact file paths and line-level references.
