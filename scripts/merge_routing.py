#!/usr/bin/env python3
"""PR merge routing — manual merge gatekeeper.

Routes pull requests through the manual merge path instead of triggering
direct merges. Dependency PRs (Dependabot, Copilot) receive the
``manual-ready`` label so Mergify's auto-merge rules (which require
``label=manual-ready``) can pick them up later.

This is the companion to the manual-ready gating added in
``.github/mergify.yml`` — all three auto-merge rules now require the
label before squashing.

Usage
-----
    # One-shot: label all eligible dependency PRs
    python -m scripts.merge_routing

    # Daemon: watch for new PRs every 2 minutes
    python -m scripts.merge_routing --daemon

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

# PR author patterns that should be routed through manual merge
DEPENDENCY_AUTHORS = ("dependabot[bot]", "github-actions[bot]")


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


def get_all_prs(repo: str, *, author: str | None = None) -> list[dict]:
    """Get all PRs (open + closed), optionally filtered by author.

    This is needed to detect already-routed PRs that are closed but unmerged.
    These PRs are often re-detected as "needing PR" on each cycle because
    the original get_open_prs() only returns open PRs.
    """
    filters = ["--state", "all", "--json", "number,title,author,labels,mergeStateStatus,state,headRefName"]
    if author:
        filters += ["--author", author]
    try:
        output = run_gh(["pr", "list", "--repo", repo] + filters, check=False)
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def check_branch_has_pr(repo: str, branch_name: str) -> dict | None:
    """Check if a branch already has an existing PR (open or closed).

    Returns the PR dict if found, None otherwise.
    """
    try:
        output = run_gh(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "all",
                "--head",
                branch_name,
                "--json",
                "number,title,state,labels,headRefName",
            ],
            check=False,
        )
        if not output or output == "[]":
            return None
        prs = json.loads(output)
        if prs:
            return prs[0]  # Return the first matching PR
        return None
    except json.JSONDecodeError:
        return None


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


# Cosmetic deprecation warnings that do not indicate a real failure
_DEPRECATION_WARNINGS = (
    "Projects (classic) is being deprecated",
    "DeprecationWarning",
)


def _is_deprecation_warning(stderr: str) -> bool:
    """Check if stderr contains only cosmetic deprecation warnings."""
    if not stderr:
        return False
    for warning in _DEPRECATION_WARNINGS:
        if warning in stderr:
            return True
    return False


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
    except subprocess.CalledProcessError as e:
        # GraphQL deprecation warnings are cosmetic — label was still applied
        if _is_deprecation_warning(e.stderr or ""):
            logger.info(
                f"Applied {MANUAL_READY_LABEL} to PR #{pr_number}"
                f" (deprecation warning, label OK)"
            )
            return True
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


def route_all_dependencies(repo: str) -> tuple[int, list[str]]:
    """Route all eligible dependency PRs through the manual merge path.

    Returns (count_of_routed, list_of_routed_pr_numbers) so callers
    can persist the routed PRs across runs.

    Uses get_all_prs() to detect both open and closed PRs. Closed-but-unmerged
    PRs that were already routed are recognized and added to routed_prs,
    preventing redundant re-detection on each cycle.
    """
    prs = get_all_prs(repo)
    if not prs:
        logger.info("No PRs found (open + closed)")
        return 0, []

    routed = 0
    routed_numbers: list[str] = []
    for pr in prs:
        pr_number = pr["number"]
        pr_state = pr.get("state", "OPEN")

        # Check if this PR is already in routed_prs (from previous runs)
        state = load_state()
        existing_routed = set(state.get("routed_prs", []))

        if str(pr_number) in existing_routed:
            # Already routed in a previous run — recognize it
            logger.debug(f"PR #{pr_number} ({pr_state}) already in routed_prs, skipping")
            if str(pr_number) not in routed_numbers:
                routed_numbers.append(str(pr_number))
            continue

        if is_dependency_pr(pr) and route_pr(repo, pr):
            routed += 1
            routed_numbers.append(str(pr_number))
            logger.info(f"PR #{pr_number} ({pr_state}) routed to manual merge")
        elif str(pr_number) not in routed_numbers:
            # PR was not newly routed but is a dependency PR
            # Check if it has the manual-ready label
            labels = [lb.get("name", "") for lb in pr.get("labels", [])]
            if MANUAL_READY_LABEL in labels:
                # Already has the label — add to routed_prs to prevent re-detection
                logger.debug(f"PR #{pr_number} ({pr_state}) already has {MANUAL_READY_LABEL}, adding to routed_prs")
                routed_numbers.append(str(pr_number))

    logger.info(f"Routed {routed}/{len(prs)} dependency PR(s) to manual merge")
    return routed, routed_numbers


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
    parser.add_argument("--interval", type=int, default=120, help="Check interval (default: 120s)")
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
                n, pr_numbers = route_all_dependencies(args.repo)

                # Merge routed PRs into state (avoid duplicates)
                existing = set(state.get("routed_prs", []))
                for prn in pr_numbers:
                    if prn not in existing:
                        state.setdefault("routed_prs", []).append(prn)
                state["last_run"] = datetime.now(tz=UTC).isoformat()
                save_state(state)

                if n:
                    logger.info(f"Routed {n} PR(s) to manual merge")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        n, pr_numbers = route_all_dependencies(args.repo)
        # Persist routed PRs in state file
        state = load_state()
        existing = set(state.get("routed_prs", []))
        for prn in pr_numbers:
            if prn not in existing:
                state.setdefault("routed_prs", []).append(prn)
        state["last_run"] = datetime.now(tz=UTC).isoformat()
        save_state(state)
        logger.info(f"Routed {n} PR(s) to manual merge" if n else "No PRs to route")

    return 0


if __name__ == "__main__":
    sys.exit(main())
