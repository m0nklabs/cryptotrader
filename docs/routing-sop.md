# GitHub Issue Routing SOP

## Cycle: Discover → Triage → Route → Link

### 1. Discover
Scan GitHub open issues for unassigned kanban tasks. Check for issues without linked kanban tasks.

### 2. Triage
- **Critical** (e.g. #303 walk-forward & lookahead-bias): Direct kapitaalrisico. Priority: high.
- **High** (e.g. #304 AI consensus, #305 PostgreSQL CI): Essentieel voor betrouwbaarheid. Priority: high.
- **Medium** (e.g. #306-#308 improvements): Nieuwe features/verbeteringen. Priority: medium.

### 3. Route
For each issue:
1. Create kanban task via `kanban_create()` with title, body (full issue description), and assignee
2. Preserve original labels (enhancement, tests, trading, priority, ai)
3. Include GitHub issue link in body metadata
4. Set workspace_kind based on task type (scratch for new work, dir for shared)

### 4. Link
- Parent task tracks all routed children in `children` array
- Each child task links back to parent via `parents` array
- GitHub issue URL preserved in kanban task body

### Priority Mapping
| GitHub label | Kanban priority | Action |
|---|---|---|
| priority: critical | high | Route immediately |
| priority: high | high | Route immediately |
| priority: medium | medium | Route on next cycle |
| priority: low | low | Route when capacity |

### Standard Cycle
1. `web_search` or `gh issue list` to find open issues
2. Filter for unassigned/no kanban task
3. Create kanban tasks in parallel (delegate_task)
4. Write/update this SOP if routing pattern changes
5. Root task completes when all children finish
