#!/usr/bin/env python3
"""Auto-rerun pending GitHub Actions workflow runs.

This script watches for "Copilot finished work on behalf of" comments
and reruns pending workflow runs for that PR's branch.

Uses the gh CLI (already authenticated locally).

Usage:
    # One-shot: check and rerun now
    python -m scripts.approve_workflows

    # Rerun all pending runs immediately
    python -m scripts.approve_workflows --approve-all

    # Daemon mode: watch for new comments every 30s
    python -m scripts.approve_workflows --daemon

Requirements:
    - gh CLI installed and authenticated (gh auth login)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_REPO = "m0nklabs/cryptotrader"
STATE_FILE = Path(__file__).parent.parent / ".workflow-approver-state.json"
COPILOT_TRIGGER = "Copilot finished work on behalf of"


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


def get_recent_comments(repo: str, since_id: int = 0) -> list[dict]:
    """Get recent issue comments containing Copilot trigger phrase."""
    try:
        output = run_gh(
            [
                "api",
                f"repos/{repo}/issues/comments",
                "--paginate",
                "--jq",
                f'[.[] | select(.id > {since_id} and (.body | contains("{COPILOT_TRIGGER}")))]',
            ],
            check=False,
        )
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def get_pr_branch(repo: str, pr_number: int) -> str | None:
    """Get the head branch for a PR."""
    try:
        return run_gh(["api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".head.ref"])
    except subprocess.CalledProcessError:
        return None


def get_pending_runs(repo: str, branch: str | None = None) -> list[dict]:
    """Get workflow runs awaiting approval (action_required status)."""
    url = f"repos/{repo}/actions/runs?status=action_required&per_page=100"
    if branch:
        url += f"&branch={branch}"
    try:
        output = run_gh(
            [
                "api",
                url,
                "--jq",
                "[.workflow_runs[] | {id: .id, name: .name, head_branch: .head_branch}]",
            ],
            check=False,
        )
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def rerun_workflow(run_id: int) -> bool:
    """Rerun a workflow run (bypasses first-time contributor approval)."""
    try:
        run_gh(["run", "rerun", str(run_id)])
        return True
    except subprocess.CalledProcessError:
        return False


def load_state() -> dict:
    """Load state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_comment_id": 0, "rerun_runs": []}


def save_state(state: dict) -> None:
    """Save state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def process_comments(repo: str, state: dict) -> int:
    """Process new Copilot comments and rerun pending workflows. Returns rerun count."""
    comments = get_recent_comments(repo, state.get("last_comment_id", 0))
    if not comments:
        return 0

    total_rerun = 0
    for comment in comments:
        comment_id = comment["id"]
        issue_url = comment.get("issue_url", "")
        try:
            pr_number = int(issue_url.split("/")[-1])
        except (ValueError, IndexError):
            continue

        logger.info(f"🔔 Copilot finished on PR #{pr_number}")
        branch = get_pr_branch(repo, pr_number)
        if not branch:
            continue

        pending = get_pending_runs(repo, branch)
        for run in pending:
            run_id = run["id"]
            if run_id in state.get("rerun_runs", []):
                continue
            if rerun_workflow(run_id):
                logger.info(f"✅ Rerun: {run['name']} (ID: {run_id})")
                state.setdefault("rerun_runs", []).append(run_id)
                total_rerun += 1

        state["last_comment_id"] = max(state.get("last_comment_id", 0), comment_id)

    # Keep list manageable
    if len(state.get("rerun_runs", [])) > 1000:
        state["rerun_runs"] = state["rerun_runs"][-500:]

    return total_rerun


def rerun_all_pending(repo: str) -> int:
    """Rerun all pending runs immediately."""
    pending = get_pending_runs(repo)
    if not pending:
        logger.info("No pending runs")
        return 0

    rerun = 0
    for run in pending:
        if rerun_workflow(run["id"]):
            logger.info(f"✅ Rerun: {run['name']} on {run['head_branch']} (ID: {run['id']})")
            rerun += 1
    logger.info(f"Reran {rerun}/{len(pending)} runs")
    return rerun


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-rerun Copilot workflow runs")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=30, help="Check interval (default: 30s)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository")
    parser.add_argument("--approve-all", action="store_true", help="Rerun all pending now")
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

    if args.approve_all:
        rerun_all_pending(args.repo)
        return 0

    if args.daemon:
        logger.info(f"Daemon mode: watching for '{COPILOT_TRIGGER}' (interval={args.interval}s)")
        try:
            while True:
                state = load_state()
                n = process_comments(args.repo, state)
                save_state(state)
                if n:
                    logger.info(f"Reran {n} run(s)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        state = load_state()
        n = process_comments(args.repo, state)
        save_state(state)
        logger.info(f"Reran {n} run(s)" if n else "No new runs to rerun")

    return 0


if __name__ == "__main__":
    sys.exit(main())
