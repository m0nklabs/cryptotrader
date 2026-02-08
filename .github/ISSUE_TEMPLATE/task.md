---
name: 📋 Task
about: A specific implementation task (suitable for AI agent delegation)
title: "[TASK] "
labels: task
assignees: ''
---

## Objective

<!-- One-sentence goal of this task -->

## Context

<!-- Link to parent Epic, related issues, or architectural docs -->

- Parent Epic: #
- Related docs: `docs/`

## Scope

### File Targets

- `path/to/file.py`

### Acceptance Criteria

- [ ]
- [ ]
- [ ]

### Non-Goals

<!-- What is explicitly out of scope -->

-

## Technical Notes

<!-- Implementation hints, patterns to follow, dependencies -->

### Patterns to Follow

<!-- Link to existing code that demonstrates the expected pattern -->

### Testing Requirements

- [ ] Unit tests added in `tests/`
- [ ] Existing tests still pass
- [ ] Mock external APIs (no real API calls in tests)

### Safety Checklist (if applicable)

- [ ] Paper trading default (`dry_run=True`)
- [ ] No hardcoded credentials
- [ ] Audit logging implemented
- [ ] AI budget caps enforced (if `core/ai/`)
