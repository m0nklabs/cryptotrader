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
| [#71 Trading System](https://github.com/m0nklabs/cryptotrader/issues/71) | Paper trading, order execution, portfolio | #29, #48, #46, #75 |
| [#69 Technical Analysis](https://github.com/m0nklabs/cryptotrader/issues/69) | Chart indicators, signal detection | #105, #107, #72, #73 |
| [#70 Market Data](https://github.com/m0nklabs/cryptotrader/issues/70) | Real-time feeds, multi-exchange | #101, #102, #103, #17 |
| [#68 Infrastructure](https://github.com/m0nklabs/cryptotrader/issues/68) | CI/CD, testing, health monitoring | #104, #106, #108, #21, #74 |
| [#76 Frontend & UI](https://github.com/m0nklabs/cryptotrader/issues/76) | Dashboard, order entry, mobile | #77, #78, #79, #80, #81, #107 |
| [#205 Multi-Brain AI](https://github.com/m0nklabs/cryptotrader/issues/205) | LLM orchestration, consensus, AI API | Providers, Roles, Consensus, API, Frontend |

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

### Agent Configuration Files

This repo no longer keeps active Copilot agent definitions in `.github/agents/`.

The single source of truth for MARK1 is `/home/flip/github-copilot-config/.github/agents/MARK1.md`.

Legacy sync script:

```bash
./scripts/sync_agents_from_central.sh
```

The script is intentionally deprecated and must not recreate local agent copies.

## Automated Copilot Assignment

A GitHub Action automatically assigns Copilot to the highest priority issue when no active Copilot PR exists.

**Workflow:** `.github/workflows/copilot-auto-assign.yml`

### Triggers

| Trigger | Frequency |
|---------|-----------|
| Schedule | Every 2 hours |
| Manual | `workflow_dispatch` |
| PR closed | When any PR is closed/merged |

### Priority Algorithm

Issues are scored and sorted (lowest score = highest priority):

1. **Priority labels** (if present):
   - `priority:critical` → score 0
   - `priority:high` → score 100
   - `priority:medium` → score 200
   - `priority:low` → score 300

2. **EPIC membership** (adds to score):
   - #71 Trading System → +1
   - #70 Market Data → +2
   - #69 Technical Analysis → +3
   - #68 Infrastructure → +4
   - #76 Frontend & UI → +5

3. **Issue age**: older issues get slight priority boost

### Exclusions

The workflow skips issues that:
- Are already assigned to Copilot
- Have `🎯` or `EPIC` in title
- Have `[blocked]` or `[wip]` in title
- Are pull requests

### Manual Override

To prioritize a specific issue, add `priority:critical` label:

```bash
gh issue edit <ISSUE#> --add-label "priority:critical"
```

To block an issue from auto-assignment:

```bash
# Rename with [blocked] prefix
gh issue edit <ISSUE#> --title "[blocked] Original title"
```

### Monitoring

View workflow runs:
```bash
gh run list --workflow=copilot-auto-assign.yml
gh run view <RUN_ID>
```

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

## Stale PR Recovery

When a Copilot PR is closed without merge (e.g., "Outdated branch", merge conflicts, rate limits), the linked issue becomes orphaned. Follow this procedure to recover:

### Detection

```bash
# Find closed unmerged PRs
gh pr list --repo m0nk111/cryptotrader --state closed --json number,title,mergedAt \
  | jq '.[] | select(.mergedAt == null)'
```

### Recovery Flow

```
┌─────────────────────────────────────────────────────────┐
│              STALE PR RECOVERY FLOW                      │
└─────────────────────────────────────────────────────────┘

     ┌───────────────────────┐
     │ 1. Find closed PRs    │
     │    without merge      │
     └───────────┬───────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │ 2. Identify linked    │
     │    issue (Fixes #XX)  │
     └───────────┬───────────┘
                 │
                 ▼
     ┌───────────────────────┐     Already done?
     │ 3. Check if issue     │─────────────────┐
     │    was implemented    │                 │
     └───────────┬───────────┘                 │
                 │ No                          │ Yes
                 ▼                             ▼
     ┌───────────────────────┐     ┌───────────────────┐
     │ 4. Close old issue    │     │ Close issue as    │
     │    (not_planned)      │     │ completed         │
     └───────────┬───────────┘     └───────────────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │ 5. Create new issue   │
     │    with [v2] suffix   │
     └───────────┬───────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │ 6. Link to parent     │
     │    EPIC               │
     └───────────┬───────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │ 7. Update EPIC body   │
     │    with new issue #   │
     └───────────┬───────────┘
                 │
                 ▼
     ┌───────────────────────┐
     │ 8. Assign to agent    │
     │    (@copilot mention) │
     └───────────────────────┘
```

### New Issue Template (v2)

```markdown
## Summary
[Original description]

> Supersedes #XX (stale Copilot PR)

## Scope
[Original scope]

## Acceptance criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Parent Epic
EPIC #YY — [Epic Name]
```

### Commands

```bash
# 1. Close old issue
gh issue close <OLD#> --reason "not planned" --comment "Superseded by #NEW"

# 2. Create new issue
gh issue create --title "Feature name [v2]" --body "..." --label enhancement

# 3. Update EPIC body (manual or via API)
gh issue edit <EPIC#> --body "..."

# 4. Assign Copilot (must @mention in comment)
gh issue comment <NEW#> --body "@copilot please implement this issue"
```

### Naming Convention

| Original Issue | New Issue |
|----------------|------------|
| #45 Extended indicators | #105 Extended indicators [v2] |
| #31 Automated tests | #108 Automated tests [v2] |

## Agent Assignment Criteria

| Criteria | Assign to |
|----------|-----------|
| Complex, multi-file | Copilot |
| Frontend-heavy | Copilot |
| Pure Python, isolated | Agent-Forge |
| Cost-sensitive | Agent-Forge |

## Orchestration log (newest-first)

## 2025-12-25
- Implemented stale PR recovery procedure
- Closed old issues with stale PRs: #45, #31, #33, #25, #4, #26, #28, #30
- Created new [v2] issues:
  - #101 Dynamic market-cap ranking [v2] (was #30) → EPIC #70
  - #102 Real-time WebSocket updates [v2] (was #26) → EPIC #70
  - #103 Multi-exchange support [v2] (was #28) → EPIC #70
  - #104 Minimal quality gate [v2] (was #4) → EPIC #68
  - #105 Extended indicators [v2] (was #45) → EPIC #69
  - #106 System health panel [v2] (was #33) → EPIC #68
  - #107 Technical indicators chart [v2] (was #25) → EPIC #69/76
  - #108 Automated tests + CI [v2] (was #31) → EPIC #68
- Updated all EPICs with new issue references
- Added EPIC #76 (Frontend & UI) to documentation
- Documented Stale PR Recovery flow in ORCHESTRATION.md

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
