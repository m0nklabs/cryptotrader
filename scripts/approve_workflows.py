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

    # Daemon mode: watch for new comments every 2 mins
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


def get_copilot_prs_with_finished_work(repo: str) -> list[dict]:
    """Get open PRs on copilot/* branches that have copilot_work_finished events."""
    try:
        # Get all open PRs on copilot branches
        prs_output = run_gh(
            [
                "api",
                f"repos/{repo}/pulls",
                "--jq",
                '[.[] | select(.head.ref | startswith("copilot/")) | {number: .number, branch: .head.ref}]',
            ],
            check=False,
        )
        if not prs_output or prs_output == "[]":
            return []

        prs = json.loads(prs_output)
        finished_prs = []

        for pr in prs:
            pr_number = pr["number"]
            # Check timeline for copilot_work_finished event
            timeline = run_gh(
                [
                    "api",
                    f"repos/{repo}/issues/{pr_number}/timeline",
                    "--jq",
                    '[.[] | select(.event == "copilot_work_finished")] | length',
                ],
                check=False,
            )
            if timeline and int(timeline) > 0:
                finished_prs.append(pr)

        return finished_prs
    except (json.JSONDecodeError, ValueError):
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


def request_copilot_review(repo: str, pr_number: int) -> bool:
    """Request Copilot Reviewer for a PR."""
    try:
        # Check if Copilot Reviewer already reviewed
        existing = run_gh(
            [
                "api",
                f"repos/{repo}/pulls/{pr_number}/reviews",
                "--jq",
                '[.[] | select(.user.login == "copilot-pull-request-reviewer[bot]")] | length',
            ],
            check=False,
        )

        if existing and int(existing) > 0:
            # Already reviewed, request re-review via comment
            run_gh(
                [
                    "pr",
                    "comment",
                    str(pr_number),
                    "--body",
                    "🔄 @copilot Please re-review this PR - new changes have been pushed.",
                ]
            )
            logger.info(f"🔄 Requested Copilot re-review for PR #{pr_number}")
        else:
            # Try to add as reviewer
            run_gh(
                [
                    "api",
                    f"repos/{repo}/pulls/{pr_number}/requested_reviewers",
                    "-X",
                    "POST",
                    "-f",
                    "reviewers[]=copilot-pull-request-reviewer[bot]",
                ],
                check=False,
            )
            logger.info(f"👀 Requested Copilot review for PR #{pr_number}")
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
    return {"last_comment_id": 0, "rerun_runs": [], "reviewed_prs": []}


def get_copilot_prs(repo: str) -> list[dict]:
    """Get open PRs from copilot/* branches."""
    try:
        output = run_gh(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--json",
                "number,headRefName,statusCheckRollup",
                "--jq",
                '[.[] | select(.headRefName | startswith("copilot/"))]',
            ],
            check=False,
        )
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def pr_checks_passed(pr: dict) -> bool:
    """Check if all CI checks passed for a PR."""
    checks = pr.get("statusCheckRollup", [])
    if not checks:
        return False
    for check in checks:
        status = check.get("status", "")
        conclusion = check.get("conclusion", "")
        # Skip pending checks
        if status not in ("COMPLETED", "completed"):
            return False
        # Check conclusion
        if conclusion not in ("SUCCESS", "success", "NEUTRAL", "neutral", "SKIPPED", "skipped"):
            return False
    return True


def save_state(state: dict) -> None:
    """Save state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def process_copilot_prs(repo: str, state: dict) -> int:
    """Process PRs where Copilot has finished work. Returns rerun count."""
    finished_prs = get_copilot_prs_with_finished_work(repo)
    if not finished_prs:
        return 0

    total_rerun = 0
    for pr in finished_prs:
        pr_number = pr["number"]
        branch = pr["branch"]
        pr_key = f"pr_{pr_number}"

        # Skip if we already processed this PR in this session
        if pr_key in state.get("processed_prs", []):
            continue

        logger.info(f"🔔 Copilot finished on PR #{pr_number} ({branch})")

        # Request Copilot Reviewer for this PR
        if pr_key not in state.get("reviewed_prs", []):
            request_copilot_review(repo, pr_number)
            state.setdefault("reviewed_prs", []).append(pr_key)

        # Rerun pending workflows for this branch
        pending = get_pending_runs(repo, branch)
        for run in pending:
            run_id = run["id"]
            if run_id in state.get("rerun_runs", []):
                continue
            if rerun_workflow(run_id):
                logger.info(f"✅ Rerun: {run['name']} (ID: {run_id})")
                state.setdefault("rerun_runs", []).append(run_id)
                total_rerun += 1

        # Mark PR as processed for this session
        state.setdefault("processed_prs", []).append(pr_key)

    # Keep lists manageable
    if len(state.get("rerun_runs", [])) > 1000:
        state["rerun_runs"] = state["rerun_runs"][-500:]
    if len(state.get("reviewed_prs", [])) > 500:
        state["reviewed_prs"] = state["reviewed_prs"][-250:]
    if len(state.get("processed_prs", [])) > 200:
        state["processed_prs"] = state["processed_prs"][-100:]

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
    parser.add_argument("--interval", type=int, default=120, help="Check interval (default: 120s)")
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
        logger.info(f"Daemon mode: watching for copilot_work_finished events (interval={args.interval}s)")
        try:
            while True:
                state = load_state()
                n = process_copilot_prs(args.repo, state)
                save_state(state)
                if n:
                    logger.info(f"Reran {n} run(s)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        state = load_state()
        n = process_copilot_prs(args.repo, state)
        save_state(state)
        logger.info(f"Reran {n} run(s)" if n else "No new runs to rerun")

    return 0


if __name__ == "__main__":
    sys.exit(main())
