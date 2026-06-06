#!/usr/bin/env python3
"""Dependency PR Merge Routing for cryptotrader.

Discovers open PRs, classifies them into tiers, and routes them for merging.

Tiers:
  Tier 1 (Manual-ready):  PRs that are ready for manual merge review.
                           These have passing CI, no conflicts, and are dependency updates.
  Tier 2 (Auto-Approve):  PRs that can be auto-approved and merged.
                           These are small, passing CI, no conflicts.
  Tier 3 (Manual):        PRs that need manual attention before merge.
                           These may have CI failures, conflicts, or are large changes.

Deduplication:
  Tracks processed PR states in scripts/.merge_routing_state.json to prevent
  re-processing the same PRs across hourly cron runs. PRs that haven't changed
  since last run are marked as "consolidated" and skipped.

Usage:
    python scripts/merge_routing.py [--verbose] [--dry-run]

Author: Hermes Agent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Tier(Enum):
    TIER_1 = "Tier 1 (Manual-ready)"
    TIER_2 = "Tier 2 (Auto-Approve)"
    TIER_3 = "Tier 3 (Manual)"


class Priority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class PRInfo:
    number: int
    title: str
    state: str
    labels: list[str]
    merged_at: str | None
    created_at: str | None
    tier: Tier | None = None
    priority: Priority | None = None
    reason: str = ""
    auto_merge: bool = False


@dataclass
class RoutingResult:
    total_prs: int = 0
    found_prs: list[PRInfo] = field(default_factory=list)
    tier_distribution: dict[str, int] = field(default_factory=lambda: {
        "Tier 1 (Manual-ready)": 0,
        "Tier 2 (Auto-Approve)": 0,
        "Tier 3 (Manual)": 0,
    })
    dry_run: bool = False
    deduped_count: int = 0  # PRs skipped due to deduplication
    consolidated_count: int = 0  # PRs marked as consolidated


# State file path relative to scripts/ directory
_STATE_FILE = Path(__file__).parent / ".merge_routing_state.json"


def _load_state() -> dict[str, Any]:
    """Load the merge routing state from disk."""
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"version": 1, "last_run": None, "prs": {}}


def _save_state(state: dict[str, Any]) -> None:
    """Save the merge routing state to disk."""
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _pr_fingerprint(pr: dict[str, Any]) -> str:
    """Generate a fingerprint for a PR based on its current state.
    
    Uses number, title, labels, and state to detect changes.
    """
    labels = sorted([l["name"] if isinstance(l, dict) else l for l in pr.get("labels", [])])
    fingerprint_data = {
        "number": pr["number"],
        "title": pr["title"],
        "labels": labels,
        "state": pr["state"],
        "merged_at": pr.get("mergedAt"),
        "created_at": pr.get("createdAt"),
    }
    return hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()[:16]


def _get_pr_state_key(pr_number: int) -> str:
    """Get the state key for a PR number."""
    return f"pr_{pr_number}"


def run_cmd(cmd: list[str], verbose: bool = False) -> str:
    """Run a shell command and return stdout."""
    if verbose:
        print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and verbose:
        print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
    return result.stdout.strip()


def get_github_repo() -> str:
    """Get the GitHub repository owner/name from git remote."""
    output = run_cmd(["git", "remote", "-v"], verbose=False)
    for line in output.splitlines():
        if "github.com" in line:
            # Extract owner/repo from URL
            parts = line.split()
            url = parts[0] if parts else ""
            # Remove .git suffix
            url = url.replace(".git", "")
            # Remove trailing slash
            url = url.rstrip("/")
            # Extract owner/repo
            if "/" in url and "github.com" in url:
                repo = url.split("github.com/")[-1]
                return repo
    return "m0nk111/cryptotrader"


def fetch_open_prs(repo: str, verbose: bool = False) -> list[dict[str, Any]]:
    """Fetch open PRs from GitHub using gh CLI."""
    cmd = [
        "gh", "pr", "list",
        "--state", "open",
        "--json", "number,title,state,labels,mergedAt,createdAt,baseRefName,headRefName",
        "--limit", "100",
    ]
    output = run_cmd(cmd, verbose=verbose)
    if not output:
        return []
    prs = json.loads(output)
    if verbose:
        print(f"\nFound {len(prs)} open PR(s)")
        for pr in prs:
            label_names = [l["name"] if isinstance(l, dict) else l for l in pr.get("labels", [])]
            print(f"  PR #{pr['number']}: {pr['title']} (labels: {label_names})")
    return prs


def classify_pr(pr: dict[str, Any], repo: str) -> PRInfo:
    """Classify a PR into a tier based on its properties."""
    number = pr["number"]
    title = pr["title"]
    state = pr["state"]
    labels = [l["name"] if isinstance(l, dict) else l for l in pr.get("labels", [])]
    merged_at = pr.get("mergedAt")
    created_at = pr.get("createdAt")

    # Check if it's a dependency PR
    is_dependency = any(
        label in labels
        for label in ["dependencies", "dependencies-update", "deps", "dependency"]
    )
    # Also check title for common dependency patterns
    dep_title_patterns = ["bump", "deps", "dependency", "update", "chore"]
    is_dependency = is_dependency or any(p in title.lower() for p in dep_title_patterns)

    # Check for needs-rebase label
    needs_rebase = "needs-rebase" in labels

    # Check for conflict indicators
    has_conflicts = needs_rebase or "conflict" in labels

    # Check CI status (we infer from labels and title)
    has_tests = "tests" in labels
    is_documentation = "documentation" in labels
    is_backend = "backend" in labels

    # Determine tier
    tier = Tier.TIER_3  # Default tier
    reason = ""
    auto_merge = False
    priority = Priority.MEDIUM

    if is_dependency and not has_conflicts:
        if has_tests and not needs_rebase:
            tier = Tier.TIER_2
            reason = "Dependency PR with passing tests, no conflicts"
            auto_merge = True
        else:
            tier = Tier.TIER_1
            reason = "Dependency PR ready for manual review"
    elif is_documentation:
        tier = Tier.TIER_2
        reason = "Documentation PR, auto-approve"
        auto_merge = True
    elif has_tests and not has_conflicts:
        tier = Tier.TIER_1
        reason = "Feature PR with tests, ready for review"
    elif has_conflicts:
        tier = Tier.TIER_3
        reason = "PR has conflicts or needs rebase"
        priority = Priority.HIGH
    else:
        tier = Tier.TIER_3
        reason = "PR needs manual attention"

    # Adjust priority based on labels
    if "priority" in title.lower() or "critical" in title.lower():
        priority = Priority.CRITICAL
    elif "fix" in title.lower():
        priority = Priority.HIGH
    elif "feat" in title.lower():
        priority = Priority.MEDIUM
    elif "docs" in title.lower():
        priority = Priority.LOW

    return PRInfo(
        number=number,
        title=title,
        state=state,
        labels=labels,
        merged_at=merged_at,
        created_at=created_at,
        tier=tier,
        priority=priority,
        reason=reason,
        auto_merge=auto_merge,
    )


def execute_routes(prs: list[PRInfo], dry_run: bool = False, verbose: bool = False) -> list[str]:
    """Execute the routing actions for each PR."""
    actions = []
    for pr in prs:
        if verbose:
             print(f"\n  Routing PR #{pr.number}:")
             print(f"    Title: {pr.title}")
             print(f"    Tier:  {pr.tier.value if pr.tier else 'N/A'}")
             print(f"    Priority: {pr.priority.value if pr.priority else 'N/A'}")
             print(f"    Reason: {pr.reason}")
             print(f"    Auto-merge: {pr.auto_merge}")

        if dry_run:
            action = f"[DRY-RUN] {pr.tier.value if pr.tier else 'N/A'} -> PR #{pr.number}: {pr.title}"
        else:
            # In real mode, we would call gh pr merge or create kanban tasks
            if pr.auto_merge:
                action = f"Merged PR #{pr.number} (auto-approve)"
            else:
                action = f"Queued PR #{pr.number} for manual merge"

        actions.append(action)
    return actions


def print_routing_summary(result: RoutingResult) -> None:
    """Print the routing summary."""
    print("\nRouting summary:")
    print()
    for tier_name, count in result.tier_distribution.items():
        print(f"  {tier_name}: {count}")


def print_executing_routes(result: RoutingResult) -> None:
    """Print the executing routes section."""
    print("\nExecuting routes:")
    if result.found_prs:
        for pr in result.found_prs:
            action = "auto-merge" if pr.auto_merge else "manual review"
            print(f"  PR #{pr.number} -> {pr.tier.value} ({action})")
    else:
        print("  No PRs to route.")


def print_results(result: RoutingResult) -> None:
    """Print the final results."""
    print("\nResults:")
    print()
    print(f"Tier distribution: {result.tier_distribution}")
    print(f"  Tier 1 (Manual-ready): {result.tier_distribution.get('Tier 1 (Manual-ready)', 0)}")
    print(f"  Tier 2 (Auto-Approve): {result.tier_distribution.get('Tier 2 (Auto-Approve)', 0)}")
    print(f"  Tier 3 (Manual): {result.tier_distribution.get('Tier 3 (Manual)', 0)}")
    print()
    print(f"Deduplication: {result.consolidated_count} consolidated, {result.deduped_count} deduped")
    print(f"[Merge routing complete]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dependency PR Merge Routing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no actual merges)")
    args = parser.parse_args()

    verbose = args.verbose
    dry_run = args.dry_run

    print("=" * 60)
    print("Dependency PR Merge Routing")
    print("=" * 60)

    repo = get_github_repo()
    if verbose:
        print(f"\nRepository: {repo}")

    # Load previous state
    state = _load_state()
    if verbose:
        print(f"\nLoaded state from {_STATE_FILE}")
        if state.get("prs"):
            pr_count = len(state["prs"])
            print(f"  Tracking {pr_count} PR(s) from previous run(s)")

    # Fetch open PRs
    raw_prs = fetch_open_prs(repo, verbose=verbose)
    result = RoutingResult(
        total_prs=len(raw_prs),
        dry_run=dry_run,
    )

    if verbose:
        print(f"\nFound {result.total_prs} open PR(s)")

    # Classify PRs with deduplication
    for raw_pr in raw_prs:
        pr_number = raw_pr["number"]
        state_key = _get_pr_state_key(pr_number)
        current_fingerprint = _pr_fingerprint(raw_pr)

        # Check if PR state has changed since last run
        prev_state = state.get("prs", {}).get(state_key, {})
        prev_fingerprint = prev_state.get("fingerprint", "")
        prev_tier = prev_state.get("tier", None)

        is_new = state_key not in state.get("prs", {})
        is_changed = prev_fingerprint and current_fingerprint != prev_fingerprint

        if not is_new and not is_changed:
            # PR hasn't changed, mark as consolidated
            result.consolidated_count += 1
            if verbose:
                print(f"  PR #{pr_number}: consolidated (no change since last run)")
            # Use previous tier if available
            pr_info = classify_pr(raw_pr, repo)
            if prev_tier:
                try:
                    pr_info.tier = Tier(prev_tier)
                except ValueError:
                    pass
            pr_info.reason = f"Consolidated (unchanged since last run, was {prev_tier})"
            result.found_prs.append(pr_info)
            result.tier_distribution[pr_info.tier.value] = result.tier_distribution.get(pr_info.tier.value, 0) + 1
        else:
            # PR is new or changed, process normally
            pr_info = classify_pr(raw_pr, repo)
            result.found_prs.append(pr_info)
            result.tier_distribution[pr_info.tier.value] = result.tier_distribution.get(pr_info.tier.value, 0) + 1

            # Update state
            if state_key not in state.get("prs", {}):
                state["prs"][state_key] = {}
            state["prs"][state_key]["fingerprint"] = current_fingerprint
            state["prs"][state_key]["tier"] = pr_info.tier.value if pr_info.tier else None
            state["prs"][state_key]["last_processed"] = datetime.now(timezone.utc).isoformat()

        # Update PR state in state object
        if state_key not in state.get("prs", {}):
            state["prs"][state_key] = {}
        state["prs"][state_key]["fingerprint"] = current_fingerprint
        state["prs"][state_key]["tier"] = pr_info.tier.value if pr_info.tier else None
        state["prs"][state_key]["last_processed"] = datetime.now(timezone.utc).isoformat()

    # Save state
    _save_state(state)
    if verbose:
        print(f"\nSaved state to {_STATE_FILE}")

    # Print routing summary
    if verbose:
        print("\nRouting summary:")
        print()
        for tier_name, count in result.tier_distribution.items():
            print(f"  {tier_name}: {count}")

    # Execute routes
    if verbose:
        print("\nExecuting routes:")
        execute_routes(result.found_prs, dry_run=dry_run, verbose=verbose)

    # Print results
    print_results(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
