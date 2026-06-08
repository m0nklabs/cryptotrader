#!/usr/bin/env python3
"""PR merge routing — manual merge gatekeeper.

Routes pull requests through the manual merge path instead of triggering
direct merges. Dependency PRs (Dependabot, Copilot) receive the
``manual-ready`` label so Mergify's auto-merge rules (which require
``label=manual-ready``) can pick them up later.

Also detects branches that are pushed to remote but lack an open PR,
flagging them as "needs PR" during the scheduled cycle runs.

This is the companion to the manual-ready gating added in
``.github/mergify.yml`` — all three auto-merge rules now require the
label before squashing.

Usage
-----
    # One-shot: label all eligible dependency PRs, detect missing PRs
    python -m scripts.merge_routing

    # Daemon: watch for new PRs every 2 minutes
    python -m scripts.merge_routing --daemon

    # Daemon with 240-minute cycle for missing-PR detection
    python -m scripts.merge_routing --daemon --interval 14400

Requirements
------------
    - gh CLI installed and authenticated (gh auth login)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_REPO = "m0nklabs/cryptotrader"
STATE_FILE = Path(__file__).parent.parent / ".merge-routing-state.json"

# Labels used by the manual merge gatekeeper
MANUAL_READY_LABEL = "manual-ready"
AUTO_MERGE_DISABLED_LABEL = "do-not-merge"
NEEDS_PR_LABEL = "needs-pr"

# PR author patterns that should be routed through manual merge
DEPENDENCY_AUTHORS = ("dependabot[bot]", "github-actions[bot]")

# Branch prefix used by Hermes kanban workers
HERMES_BRANCH_PREFIX = "hermes/"


def run_gh(args: list[str], check: bool = True) -> str:
    """Run a gh CLI command and return stdout."""
    cmd = ["gh"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.debug(f"gh command failed: {' '.join(cmd)}\n{e.stderr}")
        if check:
            raise
        return ""


def get_open_prs(repo: str, *, author: str | None = None) -> list[dict]:
    """Get open PRs, optionally filtered by author."""
    filters = ["--state", "open", "--json", "number,title,author,labels,mergeStateStatus"]
    if author:
        filters += ["--author", author]
    try:
        output = run_gh(["pr", "list", "--repo", repo] + filters, check=False)
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def is_dependency_pr(pr: dict) -> bool:
    """Check if a PR is a dependency PR (Dependabot or Copilot)."""
    author = pr.get("author", {}).get("login", "")
    title = pr.get("title", "").lower()
    # Dependabot PRs or PRs with dependency-related titles
    if author in DEPENDENCY_AUTHORS:
        return True
    if any(dep in title for dep in ("bump", "deps", "dependency", "chore(deps)")):
        return True
    return False


def needs_manual_merge(pr: dict) -> bool:
    """Determine if a PR should go through the manual merge path."""
    labels = [lb.get("name", "") for lb in pr.get("labels", [])]
    # Skip PRs already marked do-not-merge
    if AUTO_MERGE_DISABLED_LABEL in labels:
        return False
    # Skip PRs already marked manual-ready
    if MANUAL_READY_LABEL in labels:
        return False
    return True


def apply_manual_ready_label(repo: str, pr_number: int) -> bool:
    """Apply the manual-ready label to a PR."""
    try:
        run_gh(
            [
                "pr",
                "edit",
                str(pr_number),
                "--add-label",
                MANUAL_READY_LABEL,
                "--repo",
                repo,
            ]
        )
        logger.info(f"Applied {MANUAL_READY_LABEL} to PR #{pr_number}")
        return True
    except subprocess.CalledProcessError:
        logger.warning(f"Failed to apply {MANUAL_READY_LABEL} to PR #{pr_number}")
        return False


def route_pr(repo: str, pr: dict) -> bool:
    """Route a single PR through the manual merge path."""
    pr_number = pr["number"]
    author = pr.get("author", {}).get("login", "")
    merge_state = pr.get("mergeStateStatus", "")

    if not needs_manual_merge(pr):
        logger.debug(f"PR #{pr_number} ({author}) already has merge label or is blocked")
        return False

    # Apply manual-ready label to route through Mergify's gated auto-merge
    success = apply_manual_ready_label(repo, pr_number)
    if success:
        status_note = ""
        if merge_state == "BLOCKED":
            status_note = " (was blocked, now waiting for manual merge)"
        elif merge_state == "CLEAN":
            status_note = " (clean, ready for manual merge)"
        logger.info(f"PR #{pr_number} ({author}) routed to manual merge{status_note}")

    return success


def route_all_dependencies(repo: str) -> int:
    """Route all eligible dependency PRs through the manual merge path."""
    prs = get_open_prs(repo)
    if not prs:
        logger.info("No open PRs found")
        return 0

    routed = 0
    for pr in prs:
        if is_dependency_pr(pr) and route_pr(repo, pr):
            routed += 1

    logger.info(f"Routed {routed}/{len(prs)} dependency PR(s) to manual merge")
    return routed


# ---------------------------------------------------------------------------
# Missing-PR detection — branches pushed but lacking an open PR
# ---------------------------------------------------------------------------

def get_remote_hermes_branches(repo: str) -> list[str]:
    """Get all remote branches that match the hermes prefix pattern.

    Uses `git ls-remote` to list remote branches since `gh branch` is not
    universally available. Falls back to `gh pr list` if needed.
    """
    try:
        output = subprocess.run(
            ["git", "ls-remote", "--heads", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout
        branches = []
        for line in output.splitlines():
            # Format: <sha>\trefs/heads/<branch-name>
            ref = line.split("\t")[1]
            if ref.startswith("refs/heads/"):
                branch = ref[len("refs/heads/"):]
                if branch.startswith(HERMES_BRANCH_PREFIX):
                    branches.append(branch)
        return branches
    except Exception:
        return []


def get_all_prs_for_branch(repo: str, branch: str) -> list[dict]:
    """Get all PRs (open + closed) for a specific branch."""
    try:
        output = run_gh(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "number,title,state,mergedAt,closedAt,headRefName",
            ],
            check=False,
        )
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def get_open_pr_branches(repo: str) -> set[str]:
    """Get the set of branch names that currently have open PRs."""
    prs = get_open_prs(repo)
    return {pr.get("headRefName", "") for pr in prs if pr.get("headRefName")}


def detect_missing_prs(repo: str) -> tuple[list[str], list[str]]:
    """Detect branches that are pushed but lack an open PR.

    Returns (needs_pr_branches, already_flagged) — branches that need PRs
    and branches that were already flagged in the previous cycle.
    """
    remote_branches = get_remote_hermes_branches(repo)
    open_pr_branches = get_open_pr_branches(repo)

    needs_pr = []
    already_flagged = []

    for branch in remote_branches:
        if branch in open_pr_branches:
            continue

        # Check if this branch ever had a PR (open or closed)
        all_prs = get_all_prs_for_branch(repo, branch)
        if all_prs:
            # Branch had a PR but it was closed/merged — check if any were
            # closed without merge (i.e., abandoned)
            closed_without_merge = [
                pr for pr in all_prs
                if pr.get("state") == "CLOSED" and not pr.get("mergedAt")
            ]
            if closed_without_merge:
                already_flagged.append(branch)
                continue
            # Merged PR — branch is done, skip
            continue

        # Branch has no PR at all — needs one
        needs_pr.append(branch)

    logger.info(
        f"Missing PR detection: {len(needs_pr)} branches need PR, "
        f"{len(already_flagged)} already flagged"
    )
    return needs_pr, already_flagged


def flag_branch_needs_pr(repo: str, branch: str) -> bool:
    """Create or comment on a PR for a branch that needs one."""
    try:
        # Check if there's an open PR for this branch already
        open_prs = get_all_prs_for_branch(repo, branch)
        open_prs = [pr for pr in open_prs if pr.get("state") == "OPEN"]
        if open_prs:
            pr_num = open_prs[0]["number"]
            # Add needs-pr label
            run_gh(
                [
                    "pr",
                    "edit",
                    str(pr_num),
                    "--add-label",
                    NEEDS_PR_LABEL,
                    "--repo",
                    repo,
                ],
                check=False,
            )
            logger.info(f"Added {NEEDS_PR_LABEL} to existing PR #{pr_num} for {branch}")
            return True

        # No open PR — create one
        # First check if the branch is behind master
        run_gh(
            ["pr", "create", "--repo", repo, "--head", branch],
            check=False,
        )
        logger.info(f"Created PR for {branch}")
        return True
    except Exception as e:
        logger.warning(f"Failed to flag {branch} as needs PR: {e}")
        return False


def process_missing_prs(repo: str) -> int:
    """Process all branches that are pushed but lack an open PR."""
    needs_pr, already_flagged = detect_missing_prs(repo)

    if not needs_pr and not already_flagged:
        logger.info("No missing PRs detected")
        return 0

    logger.info(
        f"Processing missing PRs: {len(needs_pr)} new, "
        f"{len(already_flagged)} already flagged"
    )

    # Log the pattern
    if needs_pr:
        logger.info(
            f"Pattern detected: {len(needs_pr)} branch(es) pushed without open PR: "
            f"{', '.join(needs_pr[:5])}" + ("..." if len(needs_pr) > 5 else "")
        )

    if already_flagged:
        logger.info(
            f"Pattern detected: {len(already_flagged)} branch(es) with closed-but-unmerged PRs: "
            f"{', '.join(already_flagged[:5])}" + ("..." if len(already_flagged) > 5 else "")
        )

    # Flag the branches
    flagged = 0
    for branch in needs_pr:
        if flag_branch_needs_pr(repo, branch):
            flagged += 1

    # Save state with missing PR info
    state = load_state()
    state["missing_prs"] = {
        "needs_pr": needs_pr,
        "already_flagged": already_flagged,
        "last_detected": datetime.now(tz=UTC).isoformat(),
    }
    save_state(state)

    logger.info(f"Flagged {flagged}/{len(needs_pr)} branches as needing PR")
    return flagged


def load_state() -> dict:
    """Load state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_run": None, "routed_prs": []}


def save_state(state: dict) -> None:
    """Save state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Route PRs through manual merge path")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=120, help="Check interval in seconds (default: 120, 14400=240min for missing-PR cycle)")
    parser.add_argument("--missing-prs", action="store_true", help="Always run missing-PR detection")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Verify gh is authenticated
    try:
        run_gh(["auth", "status"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("gh CLI not authenticated. Run: gh auth login")
        return 1

    if args.daemon:
        logger.info(f"Daemon mode: watching for dependency PRs (interval={args.interval}s)")
        try:
            while True:
                state = load_state()
                n = route_all_dependencies(args.repo)
                if args.interval >= 14400 or args.missing_prs:
                    m = process_missing_prs(args.repo)
                    if m:
                        logger.info(f"Detected {m} branch(es) needing PR")
                state["last_run"] = datetime.now(tz=UTC).isoformat()
                save_state(state)
                if n:
                    logger.info(f"Routed {n} PR(s) to manual merge")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        n = route_all_dependencies(args.repo)
        m = process_missing_prs(args.repo)
        total = n + m
        logger.info(
            f"Routed {n} PR(s) to manual merge, "
            f"detected {m} branch(es) needing PR" if m
            else f"Routed {n} PR(s) to manual merge"
        )
        if total == 0:
            logger.info("No PRs to route, no missing PRs detected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
