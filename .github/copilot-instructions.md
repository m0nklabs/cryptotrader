# Repository custom instructions (Copilot)

These instructions apply to GitHub Copilot in the context of this repository.

## Primary goals

- Make the smallest correct change that satisfies the request.
- Keep the repo buildable/testable; don’t break CI.
- Prefer clarity and correctness over cleverness.

## User preferences (skeleton)

- When the user asks for a "skelet" (scaffolding), prefer a **as complete as practical** skeleton (types + interfaces + DB schema) over a minimal one, as long as it stays within the v2 scope and does not introduce live trading by default.

## Project assumptions (update when the repo grows)

- Repo name: **cryptotrader** (trading/market-data domain).
- Current focus: trading opportunities, technical analysis, and API-based autotrading.
- Frontend direction: minimal dashboard UI with sticky header/footer, MT4/5-inspired dock layout + panel-based sections, small font sizes, dark mode, collapsible panels, and a minimal settings popup in the header.
- Frontend dev server: default to port 5176 (avoid conflicts with other services on this server).
- If the repo is missing documentation (README, build steps), ask the user for the intended stack (Python/Node/etc.) before introducing major scaffolding.

## Engineering rules

- Follow existing patterns in the repo. If a pattern exists, reuse it.
- Avoid adding dependencies unless they are clearly justified; mention any new dependency explicitly.
- Don’t introduce new features beyond what is requested.
- Keep changes focused; do not reformat unrelated files.
- Don’t delete or prune documentation files/directories unless the user explicitly requests it.
- Treat `research/` as local-only scratch space and keep it out of git via `.gitignore`.
- Canonical requirements must be written into `docs/*` (do not rely on references to `research/*`).

## Delegation & orchestration

- Prefer delegating module work via GitHub Issues/PRs over doing large coding tasks in the coordinator role.
- Maintain `docs/ORCHESTRATION.md` as the process/log for delegation.

## Safety & secrets

- Never commit secrets (API keys, exchange credentials, private keys). Use environment variables and `.env.example` only.
- Don’t log sensitive values.
- Don’t delete or rewrite existing local secret files unless explicitly requested; prefer hardening via `.gitignore` and templates.
- If adding trading/execution logic, default to **paper-trading / dry-run** unless the user explicitly requests live trading.

## Validation

- Always run the most relevant tests/lint/build checks that exist in the repo.
- If no tests exist for changed behavior and the repo has a test framework, add/extend tests.
- Prefer fast, targeted test runs first; then broader checks if available.

## Developer environment

- If the integrated terminal is unstable/crashing, prefer disabling GPU acceleration in workspace settings (`terminal.integrated.gpuAcceleration`: `"off"`).

## Communication in PRs/changes

- Summarize what changed, where, and how to validate.
- Call out any assumptions or risks (especially around trading, money movement, and data integrity).

## Git workflow

- If the user explicitly asks to commit and push changes to GitHub, push directly to the default branch in this repository (no PR/feature branch) unless the user asks otherwise.

## GitHub Copilot Coding Agent

- To activate the Copilot Coding Agent on an issue or PR, you **must** mention `@copilot` in a comment.
- Using MCP tools like `assign_copilot_to_issue` alone is insufficient — the agent only starts work when explicitly mentioned.
- Example: "@copilot please implement the missing tests for this PR."
