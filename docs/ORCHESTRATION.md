# Orchestration & Delegation

This document defines how work is delegated to agents and tracked via GitHub Issues/PRs.

## Principles

- Keep coding in the coordinator role minimal.
- Prefer delegation via well-scoped issues (one module/work package per issue).
- Canonical requirements live in `docs/*`.
- `research/` is local-only and should not be required by delegated agents.
- Default to paper-trading / dry-run.

## Issue Hierarchy: Epics & Sub-issues

We use GitHub's native sub-issue feature for hierarchical planning:

```
🎯 EPIC (parent issue)
├── Sub-issue #1
├── Sub-issue #2
└── Sub-issue #3
```

### Epic Structure

| Epic | Focus | Issues |
|------|-------|--------|
| [#71 Trading System](https://github.com/m0nk111/cryptotrader/issues/71) | Paper trading, order execution, portfolio | #29, #48, #46 |
| [#69 Technical Analysis](https://github.com/m0nk111/cryptotrader/issues/69) | Chart indicators, signal detection | #45, #25 |
| [#70 Market Data](https://github.com/m0nk111/cryptotrader/issues/70) | Real-time feeds, multi-exchange | #26, #28, #30, #17 |
| [#68 Infrastructure](https://github.com/m0nk111/cryptotrader/issues/68) | CI/CD, testing, health monitoring | #31, #33, #21 |

### Epic Template

```markdown
## Vision
One-sentence goal.

## Sub-issues
- [ ] #XX Description
- [ ] #YY Description

## Scope
### Category 1
- Item
- Item

## Architecture
(ASCII diagram)

## Ideas / Backlog
- [ ] Future item
```

### Creating Sub-issues

1. Create the sub-issue first (normal issue)
2. Link to epic via GitHub UI or API:
   ```bash
   # Via GitHub CLI (when supported) or web UI
   # Issues > Epic > "Add sub-issue"
   ```

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
   - Link to parent Epic if applicable

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

## Agents

| Agent | Account | Model | Use Case |
|-------|---------|-------|----------|
| **GitHub Copilot** | `@copilot` | Cloud (GitHub) | Complex features, multi-file changes |
| **Agent-Forge** | `m0nk111-post` | Ollama (qwen3coder 30b) | Local execution, cost-free, privacy |

## Review Loop

```
┌─────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LOOP                    │
└─────────────────────────────────────────────────────────┘

     ┌──────────────┐
     │ 1. Check PRs │
     └──────┬───────┘
            │
            ▼
     ┌──────────────┐     No PRs
     │  Open PRs?   │─────────────┐
     └──────┬───────┘             │
            │ Yes                 │
            ▼                     │
     ┌──────────────┐             │
     │ 2. Review PR │             │
     └──────┬───────┘             │
            │                     │
            ▼                     │
     ┌──────────────┐             │
     │  Approved?   │             │
     └──────┬───────┘             │
            │                     │
      ┌─────┴─────┐               │
      │           │               │
     Yes          No              │
      │           │               │
      ▼           ▼               │
┌──────────┐ ┌───────────────┐    │
│ 3. Merge │ │ Request       │    │
│    PR    │ │ Changes       │    │
└────┬─────┘ └───────┬───────┘    │
     │               │            │
     │               └────────────┤
     ▼                            │
┌────────────────┐                │
│ 4. Check for   │◄───────────────┘
│    new issues  │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ 5. Assign to   │
│    agents      │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ 6. Wait for    │
│    agent work  │
└───────┬────────┘
        │
        └──────────► Loop to Step 1
```

### Loop Commands

```bash
# 1. Check open PRs
gh pr list --repo m0nk111/cryptotrader --state open

# 2. Review PR diff
gh pr diff <PR#> --repo m0nk111/cryptotrader

# 3. Merge PR (squash)
gh pr merge <PR#> --squash --repo m0nk111/cryptotrader
git pull origin master

# 4. List unassigned issues
gh issue list --repo m0nk111/cryptotrader --state open

# 5. Assign to Copilot
gh issue edit <ISSUE#> --add-assignee copilot

# 5. Assign to Agent-Forge
gh issue edit <ISSUE#> --add-assignee m0nk111-post --add-label agent-ready
```

## Conflict Prevention

When multiple agents work in parallel, merge conflicts occur. Mitigate by:

1. **Merge order**: Smallest diff first, largest last
2. **File isolation**: Avoid assigning issues that touch same files simultaneously
3. **Sequential merge**: After each merge, wait for dependent branches to rebase

### High-conflict files
- `frontend/src/App.tsx` — many features touch this
- `scripts/api_server.py` — multiple endpoints added here

## Agent Assignment Criteria

| Criteria | Assign to |
|----------|-----------|
| Complex, multi-file | Copilot |
| Frontend-heavy | Copilot |
| Pure Python, isolated | Agent-Forge |
| Cost-sensitive | Agent-Forge |

## Orchestration log (newest-first)

## 2025-12-24 (PM)
- Reorganized issues into Epic/Sub-issue hierarchy
- Created 4 Epic issues: #71 (Trading), #69 (TA), #70 (Market Data), #68 (Infrastructure)
- Linked 12 existing issues as sub-issues to their parent epics
- Documented Epic workflow in ORCHESTRATION.md

## 2025-12-24
- Merged PR #61 (/ingestion/status FastAPI endpoint)
- Merged PR #63 (Bitfinex signing helper)
- Updated PR #59 to use FastAPI endpoints (/health, /ingestion/status) with legacy fallbacks
- Created PR #66 (minimal CI workflow + test/dev-deps fixes)
- Created PR #67 (resurrected Bitfinex backoff/jitter knobs onto current master)
- Reviewed PR #60; identified resume correctness issue and prepared local fix branch
- Merged PR #37 (Golden RSI indicator)
- Merged PR #38 (Gap stats panel)
- Merged PR #39 (Trading signals engine)
- Closed PRs #34, #35, #36 (merge conflicts after sequential merges)
- Assigned Agent-Forge (m0nk111-post) to #20 (first agent-forge task)
- Documented review loop workflow

## 2025-12-21
- Updated issue #1 to reference only `docs/*` (no `research/*`).
- Added this orchestration document.
