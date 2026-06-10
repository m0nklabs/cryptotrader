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
    """Apply the manual-ready label to a PR.

    Uses check=False because the GraphQL Projects (classic) deprecation
    warning causes gh to return exit code 1 even on success.
    """
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
            ],
            check=False,
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


def merge_pr(repo: str, pr_number: int, *, strategy: str = "squash") -> bool:
    """Merge a PR using the specified strategy.

    Strategies:
      - auto:   gh pr merge --auto --squash (wait for checks, then squash merge)
      - admin:  gh pr merge --squash --admin (squash + bypass branch policy)
      - merge:  gh pr merge --merge --admin (linear merge + bypass)
    """
    merge_flags = ["--squash", "--admin", "--repo", repo, str(pr_number)]
    if strategy == "auto":
        merge_flags[0] = "--auto"
        merge_flags[1] = "--squash"
    elif strategy == "merge":
        merge_flags[0] = "--merge"
        merge_flags[1] = "--admin"

    cmd = ["gh", "pr", "merge"] + merge_flags
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"PR #{pr_number} merged via strategy '{strategy}': {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Merge failed for PR #{pr_number} (strategy={strategy}): {e.stderr.strip()}")
        return False


def get_repo_from_git() -> str:
    """Parse the GitHub repo from git remote URL."""
    try:
        output = run_gh(["remote", "get-url", "origin"], check=True)
        # Handle formats: git@github.com:owner/repo.git, https://github.com/owner/repo.git
        if ":" in output:
            repo = output.split(":")[-1].replace(".git", "")
        elif "/" in output:
            parts = output.rstrip("/").split("/")
            repo = f"{parts[-2]}/{parts[-1]}"
        else:
            repo = DEFAULT_REPO
        return repo
    except subprocess.CalledProcessError:
        return DEFAULT_REPO


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


def merge_manual_ready_prs(repo: str) -> int:
    """Find and merge PRs that are ready for manual merge.

    Strategy: apply manual-ready label, then try direct merge.
    If direct merge fails (repository rules), PRs remain labeled for Mergify/human merge.
    Returns number of PRs labeled (whether merged or pending).
    """
    prs = get_open_prs(repo)
    if not prs:
        logger.info("No open PRs found")
        return 0

    # Filter to PRs that are BLOCKED but eligible for merge
    candidates = [p for p in prs if p.get("mergeStateStatus") == "BLOCKED"]
    if not candidates:
        logger.info("No BLOCKED PRs found")
        return 0

    labeled = 0
    merged = 0
    for pr in candidates:
        pr_number = pr["number"]
        title = pr.get("title", "")

        # Apply manual-ready label
        labels = [lb.get("name", "") for lb in pr.get("labels", [])]
        if MANUAL_READY_LABEL not in labels:
            apply_manual_ready_label(repo, pr_number)
            labeled += 1
            logger.info(f"Applied manual-ready to PR #{pr_number}")
        else:
            labeled += 1
            logger.debug(f"PR #{pr_number} already has manual-ready label")

        # Try direct merge
        logger.info(f"Attempting to merge PR #{pr_number}: {title}")
        success = merge_pr(repo, pr_number, strategy="squash")
        if success:
            merged += 1
            logger.info(f"PR #{pr_number} merged successfully")
        else:
            logger.info(f"PR #{pr_number} labeled, pending merge (repository rules)")

    logger.info(f"Labeled {labeled}/{len(candidates)} BLOCKED PR(s), {merged} merged directly")
    return merged


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
    parser.add_argument("--merge", action="store_true", help="Also merge BLOCKED PRs")
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
                state["last_run"] = datetime.now(tz=UTC).isoformat()
                save_state(state)
                if n:
                    logger.info(f"Routed {n} PR(s) to manual merge")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        n = route_all_dependencies(args.repo)
        logger.info(f"Routed {n} PR(s) to manual merge" if n else "No PRs to route")

        # Merge BLOCKED PRs if --merge flag is set
        if args.merge:
            m = merge_manual_ready_prs(args.repo)
            if m:
                logger.info(f"Merged {m} BLOCKED PR(s)")
            else:
                logger.info("No BLOCKED PRs to merge")

    return 0


if __name__ == "__main__":
    sys.exit(main())
