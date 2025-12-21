# Orchestration & Delegation

This document defines how work is delegated to agents and tracked via GitHub Issues/PRs.

## Principles

- Keep coding in the coordinator role minimal.
- Prefer delegation via well-scoped issues (one module/work package per issue).
- Canonical requirements live in `docs/*`.
- `research/` is local-only and should not be required by delegated agents.
- Default to paper-trading / dry-run.

## Workflow (recommended)

1. **Define scope in docs**
   - Ensure the feature is described in `docs/ARCHITECTURE.md` and captured as a work package in `docs/TODO.md`.

2. **Create a GitHub Issue (work package)**
   - Title: `WPx — <module>`
   - Body must include:
     - Scope
     - File targets
     - Acceptance criteria
     - Explicit non-goals (e.g., no DEX/bridges)

3. **Assign to an agent / developer**
   - Agent implements on a branch and opens a PR.

4. **Pull Request requirements**
   - PR description references the issue.
   - Use `Closes #<issue>` to auto-close on merge.
   - Keep changes minimal and limited to the work package.

5. **Review & merge**
   - Validate via tests/smoke checks.
   - Ensure safety constraints are upheld.

## Issue template (copy/paste)

- Goal:
- Canonical docs:
  - `docs/ARCHITECTURE.md`
  - `docs/TODO.md`
- Scope:
- File targets:
- Acceptance criteria:
- Non-goals:

## Orchestration log (newest-first)

## 2025-12-21
- Updated issue #1 to reference only `docs/*` (no `research/*`).
- Added this orchestration document.
