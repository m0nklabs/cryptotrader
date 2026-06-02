#!/usr/bin/env python3
"""
Merge routing for dependency PRs in cryptotrader.

Routes dependency PRs into a manual gatekeeper lane.

Usage:
    python merge_routing.py [--dry-run] [--pr <number>] [--verbose] [--route-only]

Tier routing:
    Tier 1 (Manual-ready): dependabot + CI pass + no conflict + <7d old + patch/req/minor → mark ready for manual merge
    Tier 2 (Manual-ready): CI pass + no conflict + (>=7d old OR major OR 3+ deps) → mark ready for manual merge
    Tier 3 (Manual):       conflicts, failing CI, draft, do-not-merge, major core deps, >14d → notify human
"""

import subprocess
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Optional

# Configuration
WORK_DIR = Path("/home/flip/cryptotrader_hermes")
KNOWN_AUTHORS = {"dependabot[bot]", "app/dependabot", "Copilot", "github-actions[bot]", "m0nk111", "m0nk1111"}

# CI check names
CI_CHECK_MAPPING = {
    "Analyze (python)": "Backend (ruff + pytest)",
    "Analyze (javascript)": "Pre-commit checks",
    "Gitleaks": "Gitleaks",
    "CodeQL": "CodeQL",
    "Summary": "Summary",
}

REQUIRED_CHECKS = {"Backend (ruff + pytest)", "Pre-commit checks", "Gitleaks"}

# Dependency paths
DEP_PATHS = {
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    ".pre-commit-config.yaml",
    ".editorconfig",
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "Makefile",
}

FRONTEND_PATHS = {"frontend/", "frontend/package.json", "frontend/package-lock.json"}
CORE_DEPS = {"fastapi", "sqlalchemy", "pydantic", "numpy", "pandas", "uvicorn", "gunicorn"}

# Routing config
TIER1_MAX_AGE_DAYS = 7
TIER1_MAX_DEPS = 2
TIER2_HOLD_HOURS = 48
TIER3_MAX_AGE_DAYS = 14
TIER3_AUTO_MERGE_DAYS = 30
MANUAL_MERGE_LABEL = "ready-for-manual-merge"


class Tier(Enum):
    TIER_1 = 1  # Manual-ready fast lane
    TIER_2 = 2  # Manual-ready guarded lane
    TIER_3 = 3  # Manual


class Action(Enum):
    MERGE = "merge"
    AUTO_APPROVE = "auto-approve"
    COMMENT = "comment"
    ESCALATE = "escalate"
    SKIP = "skip"


class MergeRoute:
    """Single PR merge routing result."""

    def __init__(self, pr_number: int, title: str, tier: Tier, action: Action, reason: str, details: dict = None):
        self.pr_number = pr_number
        self.title = title
        self.tier = tier
        self.action = action
        self.reason = reason
        self.details = details or {}

    def __repr__(self):
        return f"MergeRoute(PR#{self.pr_number}: Tier{self.tier.value} -> {self.action.value} ({self.reason}))"


def run_cmd(cmd: str, cwd=None) -> tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(cmd, shell=True, cwd=cwd or str(WORK_DIR), capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_open_prs() -> list[dict]:
    """Get all open dependabot PRs with details."""
    rc, out, err = run_cmd(
        "gh pr list --state open --json number,title,author,createdAt,updatedAt,state,"
        "mergeStateStatus,labels,commits,statusCheckRollup,files,isDraft,body"
    )
    if rc != 0:
        print(f"Error getting PRs: {err}", file=sys.stderr)
        return []
    prs = json.loads(out)
    # Filter to dependabot PRs only
    return [pr for pr in prs if "dependabot" in pr.get("author", {}).get("login", "").lower()]


def get_pr_check_runs(pr_number: int) -> list[dict]:
    """Get check runs for a specific PR."""
    rc, out, _ = run_cmd(f"gh pr view {pr_number} --json headRefOid")
    if rc != 0:
        return []
    head_sha = json.loads(out).get("headRefOid", "")
    if not head_sha:
        return []

    rc, out, _ = run_cmd(f"gh api repos/m0nklabs/cryptotrader/commits/{head_sha}/check-runs")
    if rc != 0:
        return []

    data = json.loads(out)
    return data.get("check_runs", [])


def check_ci_status(check_runs: list[dict]) -> tuple[bool, dict[str, str]]:
    """Check if all required CI checks pass.

    Returns (all_pass, check_status_dict).
    """
    check_map = {}
    for cr in check_runs:
        name = cr.get("name", "")
        status = cr.get("status", "")

        mapped_name = CI_CHECK_MAPPING.get(name, name)
        check_map[mapped_name] = status

    all_pass = True
    for req in REQUIRED_CHECKS:
        status = check_map.get(req)
        if status not in ("completed", "success", "passed", "COMPLETED", "SUCCESS", "pass"):
            all_pass = False

    return all_pass, check_map


def is_dependabot_pr(pr: dict) -> bool:
    """Check if PR is from dependabot."""
    author = pr.get("author", {}).get("login", "")
    return "dependabot" in author.lower()


def is_known_author(pr: dict) -> bool:
    """Check if PR author is known."""
    author = pr.get("author", {}).get("login", "")
    return author in KNOWN_AUTHORS or "dependabot" in author.lower()


def is_draft(pr: dict) -> bool:
    """Check if PR is a draft."""
    return pr.get("isDraft", False)


def has_conflicts(pr: dict) -> bool:
    """Check if PR has merge conflicts."""
    return str(pr.get("mergeStateStatus") or "").upper() == "DIRTY"


def count_dep_files(pr: dict) -> int:
    """Count the number of dependency-related files changed."""
    files = pr.get("files", [])
    count = 0
    for f in files:
        filename = f.get("filename", "") if isinstance(f, dict) else str(f)
        # Only count actual dependency manifest files
        if any(filename.startswith(p) or filename.endswith(p) for p in DEP_PATHS):
            count += 1
        elif any(filename.startswith(p) for p in FRONTEND_PATHS):
            count += 1
    return count


def is_limited_scope(pr: dict) -> bool:
    """Check if PR scope is limited to dependency paths."""
    files = pr.get("files", [])
    for f in files:
        filename = f.get("filename", "") if isinstance(f, dict) else str(f)
        # Check if file is in dependency paths
        if any(filename.startswith(p) or filename.endswith(p) for p in DEP_PATHS):
            continue
        if any(filename.startswith(p) for p in FRONTEND_PATHS):
            continue
        # Any non-dependency path makes this false
        return False
    return True  # All files are dependency-related


def get_pr_age_days(pr: dict) -> int:
    """Get the age of the PR in days."""
    created = pr.get("createdAt", "")
    if not created:
        return 0
    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - created_dt).days


def classify_pr(pr: dict, check_runs: list[dict]) -> MergeRoute:
    """Classify a PR for merge routing.

    Returns a MergeRoute with tier and action.
    """
    ci_pass, check_map = check_ci_status(check_runs)
    age_days = get_pr_age_days(pr)
    num_files = count_dep_files(pr)
    is_dep = is_dependabot_pr(pr)
    dep_conflicts = has_conflicts(pr)

    # Tier 3: Manual - failing CI, conflicts, draft, too old
    if not ci_pass:
        return MergeRoute(
            pr["number"],
            pr["title"],
            Tier.TIER_3,
            Action.COMMENT,
            f"CI not passing: {[k for k,v in check_map.items() if v not in ('completed','success','passed','COMPLETED','SUCCESS','pass')]}",
            {"check_map": check_map, "ci_pass": ci_pass},
        )

    if dep_conflicts:
        return MergeRoute(
            pr["number"],
            pr["title"],
            Tier.TIER_3,
            Action.COMMENT,
            "Merge conflicts detected",
            {"check_map": check_map, "ci_pass": ci_pass, "conflicts": True},
        )

    if is_draft(pr):
        return MergeRoute(
            pr["number"],
            pr["title"],
            Tier.TIER_3,
            Action.COMMENT,
            "PR is draft",
            {"check_map": check_map, "ci_pass": ci_pass},
        )

    # Tier 1: Auto-Merge
    if (
        is_dep
        and ci_pass
        and not dep_conflicts
        and age_days < TIER1_MAX_AGE_DAYS
        and num_files <= TIER1_MAX_DEPS
        and is_limited_scope(pr)
    ):
        return MergeRoute(
            pr["number"],
            pr["title"],
            Tier.TIER_1,
            Action.MERGE,
            f"dependabot, CI pass, no conflicts, {age_days}d old, {num_files} file(s)",
            {"check_map": check_map, "ci_pass": ci_pass, "age_days": age_days, "num_files": num_files},
        )

    # Tier 2: Auto-Approve
    if ci_pass and not dep_conflicts and (age_days >= TIER1_MAX_AGE_DAYS or num_files >= 3):
        return MergeRoute(
            pr["number"],
            pr["title"],
            Tier.TIER_2,
            Action.AUTO_APPROVE,
            f"CI pass, no conflicts, {age_days}d old, {num_files} file(s)",
            {"check_map": check_map, "ci_pass": ci_pass, "age_days": age_days, "num_files": num_files},
        )

    # Fallback Tier 3 for PRs with passing CI that still miss fast-lane criteria.
    return MergeRoute(
        pr["number"],
        pr["title"],
        Tier.TIER_3,
        Action.COMMENT,
        "Does not meet auto-approval criteria",
        {"check_map": check_map, "ci_pass": ci_pass, "age_days": age_days, "num_files": num_files},
    )


# BLOCKED can remain stale even after conflict markers disappear from the PR diff.
def resolve_block_status(pr_number: int) -> tuple[bool, str]:
    """Resolve BLOCKED merge status without automatic merge actions."""
    # Check if there are actual conflict markers in the files
    rc, diff_output, _ = run_cmd(f"gh pr diff {pr_number}")
    has_conflict_markers = '"content"' in diff_output or "<<<<<<" in diff_output
    if has_conflict_markers:
        return False, f"PR #{pr_number} has real conflict markers and must be resolved by a human before manual merge."
    else:
        # No actual conflict markers, BLOCKED may be stale.
        return True, f"PR #{pr_number} BLOCKED status looks stale; review manually before merge."


def apply_merge_route(route: MergeRoute, dry_run: bool = False) -> str:
    """Apply the merge routing action for a classified PR.

    Returns a message describing what was done.
    """
    pr_num = route.pr_number

    if dry_run:
        return f"[DRY RUN] PR #{pr_num}: Tier {route.tier.value} -> {route.action.value} ({route.reason})"

    if route.action == Action.MERGE:
        # Check if BLOCKED and resolve if needed
        if route.details.get("conflicts"):
            resolved, msg = resolve_block_status(pr_num)
            if not resolved:
                return msg

        labels = [label["name"] for label in pr_get_labels(pr_num)]
        if MANUAL_MERGE_LABEL not in labels:
            run_cmd(f"gh pr edit {pr_num} --add-label {MANUAL_MERGE_LABEL}")
        return f"PR #{pr_num}: Ready for manual merge review - {route.reason}"

    elif route.action == Action.AUTO_APPROVE:
        # Never auto-approve drafts - they should be COMMENT action
        labels = [label["name"] for label in pr_get_labels(pr_num)]
        if MANUAL_MERGE_LABEL not in labels:
            run_cmd(f"gh pr edit {pr_num} --add-label {MANUAL_MERGE_LABEL}")
        return f"PR #{pr_num}: Ready for manual merge review - {route.reason}"

    elif route.action == Action.COMMENT:
        comment = f"\U0001F916 Merge routing: Tier {route.tier.value} - {route.reason}\n\n"
        comment += f"CI pass: {route.details.get('ci_pass', 'N/A')}\n"
        comment += f"Age: {route.details.get('age_days', 'N/A')} days\n"
        comment += f"Files changed: {route.details.get('num_files', 'N/A')}\n"

        run_cmd(f'gh pr comment {pr_num} --body "{comment}"')
        return f"PR #{pr_num}: Added comment (Tier {route.tier.value})"

    elif route.action == Action.ESCALATE:
        run_cmd(f'gh pr edit {pr_num} --add-label "do-not-merge"')
        return f"PR #{pr_num}: Escalated to manual review"

    return f"PR #{pr_num}: No action needed"


def pr_get_labels(pr_number: int) -> list[dict]:
    """Get labels for a PR."""
    rc, out, _ = run_cmd(f"gh pr view {pr_number} --json labels")
    if rc == 0:
        return json.loads(out).get("labels", [])
    return []


def pr_get_updated_time(pr_number: int) -> Optional[datetime]:
    """Get the updated time of a PR."""
    rc, out, _ = run_cmd(f"gh pr view {pr_number} --json updatedAt")
    if rc == 0:
        updated = json.loads(out).get("updatedAt", "")
        if updated:
            return datetime.fromisoformat(updated.replace("Z", "+00:00"))
    return None


def route_prs(
    prs: list[dict], dry_run: bool = False, verbose: bool = False, pr_number: Optional[int] = None
) -> list[MergeRoute]:
    """Route all (or specified) PRs through merge routing.

    Returns list of MergeRoute results.
    """
    if pr_number:
        prs = [p for p in prs if p["number"] == pr_number]

    routes = []
    for pr in prs:
        check_runs = get_pr_check_runs(pr["number"])
        route = classify_pr(pr, check_runs)
        routes.append(route)

        if verbose:
            print(f"PR #{pr['number']}: {pr['title']}")
            print(
                f"  Author: {pr['author']['login']}, Age: {route.details.get('age_days', '?')}d, Files: {route.details.get('num_files', '?')}"
            )
            print(f"  CI pass: {route.details.get('ci_pass', '?')}")
            print(f"  Route: Tier {route.tier.value} -> {route.action.value} ({route.reason})")
            print()

    return routes


def execute_routes(routes: list[MergeRoute], dry_run: bool = False, verbose: bool = False) -> list[str]:
    """Execute the merge routing actions for a list of routes.

    Returns list of result messages.
    """
    results = []
    for route in routes:
        result = apply_merge_route(route, dry_run)
        results.append(result)
        if verbose:
            print(f"  {result}")

    return results


def run_merge_routing(
    dry_run: bool = False, pr_number: Optional[int] = None, verbose: bool = False, route_only: bool = False
):
    """Run the full merge routing pipeline."""
    print("=" * 60)
    print("Dependency PR Merge Routing")
    print("=" * 60)

    # Get PRs
    all_prs = get_open_prs()
    print(f"\nFound {len(all_prs)} open PRs\n")

    # Route
    routes = route_prs(all_prs, dry_run=dry_run, verbose=verbose, pr_number=pr_number)

    # Summary before execution
    print("Routing summary:")
    for r in routes:
        print(f"  PR #{r.pr_number}: Tier {r.tier.value} -> {r.action.value} ({r.reason})")

    if route_only:
        print("\n[Route-only mode - no actions taken]")
        return routes

    # Execute
    print("\n" + "=" * 60)
    print("Executing routes:")
    print("=" * 60)
    results = execute_routes(routes, dry_run=dry_run, verbose=verbose)

    # Print results
    print("\n" + "=" * 60)
    print("Results:")
    print("=" * 60)
    for r in results:
        print(f"  {r}")

    # Tier distribution
    tiers = {}
    for r in routes:
        tiers[r.tier.value] = tiers.get(r.tier.value, 0) + 1

    print(f"\nTier distribution: {tiers}")
    print(f"  Tier 1 (Manual-ready): {tiers.get(1, 0)}")
    print(f"  Tier 2 (Auto-Approve): {tiers.get(2, 0)}")
    print(f"  Tier 3 (Manual): {tiers.get(3, 0)}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Merge routing for dependency PRs")
    parser.add_argument("--dry-run", action="store_true", help="Don't apply changes")
    parser.add_argument("--pr", type=int, help="Route specific PR number")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--route-only", action="store_true", help="Show routes without executing")
    args = parser.parse_args()

    run_merge_routing(
        dry_run=args.dry_run,
        pr_number=args.pr,
        verbose=args.verbose,
        route_only=args.route_only,
    )

    if args.dry_run:
        print("\n[Dry run complete - no changes applied]")
    else:
        print("\n[Merge routing complete]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
