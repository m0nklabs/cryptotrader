#!/usr/bin/env python3
"""
Auto-review logic for dependency PRs in cryptotrader.

Checks CI status and applies auto-approval or adds comments based on
the rules defined in the dependency-pr-automation skill.

Usage:
    python auto_review_deps.py [--dry-run] [--pr <number>] [--verbose]
"""

import subprocess
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Configuration
WORK_DIR = Path("/home/flip/cryptotrader")
KNOWN_AUTHORS = {"dependabot[bot]", "app/dependabot", "Copilot", "github-actions[bot]", "m0nk111", "m0nk1111"}

# CI check names - maps from actual GitHub check run names to mergify.yml expectations
CI_CHECK_MAPPING = {
    "Analyze (python)": "Backend (ruff + pytest)",
    "Analyze (javascript)": "Pre-commit checks",
    "Gitleaks": "Gitleaks",
    "CodeQL": "CodeQL",
    "Summary": "Summary",
}

# Required CI checks for auto-approval
REQUIRED_CHECKS = {"Backend (ruff + pytest)", "Pre-commit checks", "Gitleaks"}

# Dependency paths that count as limited scope
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

# Frontend paths
FRONTEND_PATHS = {"frontend/", "frontend/package.json", "frontend/package-lock.json"}

# Core dependency paths (major updates to these need manual review)
CORE_DEPS = {"fastapi", "sqlalchemy", "pydantic", "numpy", "pandas", "uvicorn", "gunicorn"}


def run_cmd(cmd: str, cwd=None) -> tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(cmd, shell=True, cwd=cwd or str(WORK_DIR), capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_open_dependabot_prs() -> list[dict]:
    """Get all open dependabot PRs with details."""
    rc, out, err = run_cmd(
        "gh pr list --state open --json number,title,author,createdAt,updatedAt,state,"
        "mergeStateStatus,labels,commits,statusCheckRollup,files,isDraft,body"
    )
    if rc != 0:
        print(f"Error getting PRs: {err}", file=sys.stderr)
        return []

    prs = json.loads(out)
    # Explicit dependabot-only filtering
    return [p for p in prs if "dependabot" in p.get("author", {}).get("login", "")]


def get_pr_check_runs(pr_number: int) -> list[dict]:
    """Get check runs for a specific PR."""
    # Get the head commit SHA
    rc, out, _ = run_cmd(f"gh pr view {pr_number} --json headRefOid")
    if rc != 0:
        return []
    head_sha = json.loads(out).get("headRefOid", "")
    if not head_sha:
        return []

    # Get check runs for the head commit
    rc, out, _ = run_cmd(f"gh api repos/m0nklabs/cryptotrader/commits/{head_sha}/check-runs")
    if rc != 0:
        return []

    data = json.loads(out)
    return data.get("check_runs", [])


def check_ci_status(check_runs: list[dict]) -> tuple[bool, dict[str, str]]:
    """Check if all required CI checks pass.

    Returns (all_pass, check_status_dict).
    """
    # Build a map of check name -> status
    check_map = {}
    for cr in check_runs:
        name = cr.get("name", "")
        status = cr.get("status", "")

        # Map actual check names to mergify expectations
        mapped_name = CI_CHECK_MAPPING.get(name, name)
        check_map[mapped_name] = status

    # Check required checks
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
    """Check if PR has merge conflicts (DIRTY status only)."""
    return str(pr.get("mergeStateStatus") or "").upper() == "DIRTY"


def count_dep_files(pr: dict) -> int:
    """Count the number of dependency manifest files changed."""
    files = pr.get("files", [])
    count = 0
    for f in files:
        filename = f.get("filename", "") if isinstance(f, dict) else str(f)
        # Only count actual dependency manifest files
        if any(filename == p or filename.endswith("/" + p) for p in DEP_PATHS):
            count += 1
        elif filename in FRONTEND_PATHS or any(filename.startswith(p) for p in FRONTEND_PATHS if p.endswith("/")):
            count += 1
    return count


def is_limited_scope(pr: dict) -> bool:
    """Check if PR scope is limited to dependency manifest files."""
    files = pr.get("files", [])
    for f in files:
        filename = f.get("filename", "") if isinstance(f, dict) else str(f)
        # Check if file is a dependency manifest file
        is_dep_file = any(filename == p or filename.endswith("/" + p) for p in DEP_PATHS)
        is_frontend_dep = filename in FRONTEND_PATHS or any(filename.startswith(p) for p in FRONTEND_PATHS if p.endswith("/"))
        
        if not (is_dep_file or is_frontend_dep):
            return False  # Any non-dependency file makes this false
    return True  # All files are dependency-related


def get_pr_age_days(pr: dict) -> int:
    """Get the age of the PR in days."""
    created = pr.get("createdAt", "")
    if not created:
        return 0
    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - created_dt).days


def _classification_result(
    pr: dict,
    *,
    tier: int,
    action: str,
    reason: str,
    ci_pass: bool,
    check_map: dict[str, str],
    age_days: int,
    num_files: int,
) -> dict:
    return {
        "pr": pr,
        "tier": tier,
        "action": action,
        "reason": reason,
        "ci_pass": ci_pass,
        "check_map": check_map,
        "age_days": age_days,
        "num_files": num_files,
    }


def classify_pr(pr: dict, check_runs: list[dict]) -> dict:
    """Classify a PR for auto-review.

    Returns a dict with classification details.
    """
    ci_pass, check_map = check_ci_status(check_runs)
    age_days, num_files = get_pr_age_days(pr), count_dep_files(pr)
    is_dep = is_dependabot_pr(pr)

    if not ci_pass:
        return _classification_result(
            pr,
            tier=3,
            action="comment",
            reason="CI checks not all passing",
            ci_pass=ci_pass,
            check_map=check_map,
            age_days=age_days,
            num_files=num_files,
        )
    elif has_conflicts(pr):
        return _classification_result(
            pr,
            tier=3,
            action="comment",
            reason="Merge conflicts detected",
            ci_pass=ci_pass,
            check_map=check_map,
            age_days=age_days,
            num_files=num_files,
        )
    elif is_draft(pr):
        return _classification_result(
            pr,
            tier=3,
            action="comment",
            reason="PR is draft",
            ci_pass=ci_pass,
            check_map=check_map,
            age_days=age_days,
            num_files=num_files,
        )
    elif is_dep and ci_pass and not has_conflicts(pr) and not is_draft(pr) and age_days < 7 and num_files <= 2 and is_limited_scope(pr):
        # Tier 1: Auto-Merge
        return _classification_result(
            pr,
            tier=1,
            action="merge",
            reason=f"dependabot, CI pass, no conflicts, {age_days}d old, {num_files} file(s)",
            ci_pass=ci_pass,
            check_map=check_map,
            age_days=age_days,
            num_files=num_files,
        )
    elif ci_pass and not has_conflicts(pr) and not is_draft(pr) and (age_days >= 7 or num_files >= 3):
        # Tier 2: Auto-Approve
        return _classification_result(
            pr,
            tier=2,
            action="auto-approve",
            reason=f"CI pass, no conflicts, {age_days}d old, {num_files} file(s)",
            ci_pass=ci_pass,
            check_map=check_map,
            age_days=age_days,
            num_files=num_files,
        )
    else:
        # Tier 3: Manual
        return _classification_result(
            pr,
            tier=3,
            action="comment",
            reason="Does not meet auto-approval criteria",
            ci_pass=ci_pass,
            check_map=check_map,
            age_days=age_days,
            num_files=num_files,
        )


def apply_action(pr_class: dict, dry_run: bool = False) -> str:
    """Apply the auto-review action for a classified PR.

    Returns a message describing what was done.
    """
    pr = pr_class["pr"]
    pr_num = pr["number"]
    action = pr_class["action"]
    tier = pr_class["tier"]
    reason = pr_class["reason"]

    if dry_run:
        return f"[DRY RUN] PR #{pr_num}: Tier {tier} -> {action} ({reason})"

    if action == "merge":
        # Manual gatekeeper mode: mark the PR for manual merge review.
        labels = [label["name"] for label in pr.get("labels", [])]
        if "ready-for-manual-merge" not in labels:
            run_cmd(f"gh pr edit {pr_num} --add-label ready-for-manual-merge")
        return f"PR #{pr_num}: Ready for manual merge review"

    elif action == "auto-approve":
        # Manual gatekeeper mode: mark the PR for manual merge review.
        labels = [label["name"] for label in pr.get("labels", [])]
        if "ready-for-manual-merge" not in labels:
            run_cmd(f"gh pr edit {pr_num} --add-label ready-for-manual-merge")
        return f"PR #{pr_num}: Ready for manual merge review"

    elif action == "comment":
        # Add a comment - explicit draft handling
        if is_draft(pr):
            comment = f"🤖 Auto-review: Tier {tier} - Draft PR detected\n\n"
            comment += "This PR is in draft status and will not be auto-approved.\n"
        else:
            comment = f"🤖 Auto-review: Tier {tier} - {reason}\n\n"
            comment += f"CI pass: {pr_class['ci_pass']}\n"
            comment += f"Age: {pr_class['age_days']} days\n"
            comment += f"Files changed: {pr_class['num_files']}\n"

        run_cmd(f'gh pr comment {pr_num} --body "{comment}"')
        return f"PR #{pr_num}: Added comment (Tier {tier})"

    return f"PR #{pr_num}: No action needed"


def run_auto_review(dry_run: bool = False, pr_number: int = None, verbose: bool = False):
    """Run the auto-review logic for dependency PRs."""
    print("=" * 60)
    print("Dependency PR Auto-Review")
    print("=" * 60)

    # Get PRs
    if pr_number:
        all_prs = get_open_dependabot_prs()
        prs = [all_prs[0]] if all_prs else []
        # Filter by number if specified
        prs = [p for p in prs if p["number"] == pr_number]
    else:
        prs = get_open_dependabot_prs()

    print(f"\nFound {len(prs)} open dependabot PRs\n")

    results = []
    for pr in prs:
        # Get check runs
        check_runs = get_pr_check_runs(pr["number"])

        # Classify
        pr_class = classify_pr(pr, check_runs)

        if verbose:
            print(f"PR #{pr['number']}: {pr['title']}")
            print(f"  Author: {pr['author']['login']}")
            print(f"  Age: {pr_class['age_days']} days, Files: {pr_class['num_files']}")
            print(f"  CI pass: {pr_class['ci_pass']}")
            print(f"  Checks: {pr_class['check_map']}")
            print(f"  Merge status: {pr['mergeStateStatus']}")
            print(f"  Tier: {pr_class['tier']}, Action: {pr_class['action']}")
            print(f"  Reason: {pr_class['reason']}")
            print()

        # Apply action
        result = apply_action(pr_class, dry_run)
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    for r in results:
        print(f"  {r}")

    # Print tier distribution without recomputing classifications
    tiers = {}
    classifications = []
    for pr in prs:
        check_runs = get_pr_check_runs(pr["number"])
        pr_class = classify_pr(pr, check_runs)
        classifications.append(pr_class)
        tier = pr_class["tier"]
        tiers[tier] = tiers.get(tier, 0) + 1

    print(f"\nTier distribution: {tiers}")
    print(f"  Tier 1 (Manual-ready): {tiers.get(1, 0)}")
    print(f"  Tier 2 (Auto-Approve): {tiers.get(2, 0)}")
    print(f"  Tier 3 (Manual): {tiers.get(3, 0)}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Auto-review dependency PRs")
    parser.add_argument("--dry-run", action="store_true", help="Don't apply changes")
    parser.add_argument("--pr", type=int, help="Review specific PR number")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    run_auto_review(dry_run=args.dry_run, pr_number=args.pr, verbose=args.verbose)

    # Exit with appropriate code
    if args.dry_run:
        print("\n[Dry run complete - no changes applied]")
    else:
        print("\n[Auto-review complete]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
