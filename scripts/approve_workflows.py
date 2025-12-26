#!/usr/bin/env python3
"""Auto-approve pending GitHub Actions workflow runs.

This script polls for workflow runs awaiting approval and approves them automatically.
Uses the `gh` CLI which should already be authenticated.

Usage:
    # One-shot approval
    python -m scripts.approve_workflows

    # Continuous daemon mode (checks every 60 seconds)
    python -m scripts.approve_workflows --daemon

    # Custom interval
    python -m scripts.approve_workflows --daemon --interval 30

Requirements:
    - gh CLI installed and authenticated (`gh auth login`)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_REPO = "m0nklabs/cryptotrader"


class WorkflowApprover:
    """Approves pending GitHub Actions workflow runs using gh CLI."""

    def __init__(self, repo: str):
        """Initialize the approver.

        Args:
            repo: Repository in 'owner/repo' format
        """
        self.repo = repo

    def _run_gh(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a gh CLI command.

        Args:
            args: Arguments to pass to gh
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result
        """
        cmd = ["gh"] + args
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def get_pending_runs(self) -> list[dict]:
        """Get workflow runs awaiting approval.

        Returns:
            List of pending workflow run objects
        """
        try:
            result = self._run_gh(
                [
                    "run",
                    "list",
                    "--repo",
                    self.repo,
                    "--status",
                    "action_required",
                    "--limit",
                    "100",
                    "--json",
                    "databaseId,name,headBranch,event,workflowName",
                ]
            )
            return json.loads(result.stdout) if result.stdout else []
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to fetch pending runs: {e.stderr}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse gh output: {e}")
            return []

    def approve_run(self, run_id: int, run_name: str) -> bool:
        """Approve a specific workflow run.

        Args:
            run_id: The workflow run ID
            run_name: Display name for logging

        Returns:
            True if approved successfully
        """
        try:
            self._run_gh(
                ["run", "watch", str(run_id), "--repo", self.repo, "--exit-status"], check=False
            )  # watch doesn't approve, we need the API

            # Use gh api to approve
            result = self._run_gh(
                ["api", "--method", "POST", f"/repos/{self.repo}/actions/runs/{run_id}/approve"], check=False
            )

            if result.returncode == 0:
                logger.info(f"✅ Approved: {run_name} (run_id={run_id})")
                return True
            elif "already been approved" in result.stderr.lower() or "404" in result.stderr:
                logger.debug(f"Already approved or not found: {run_name}")
                return False
            else:
                logger.error(f"Failed to approve {run_name}: {result.stderr}")
                return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed for {run_name}: {e.stderr}")
            return False

    def approve_all_pending(self) -> tuple[int, int]:
        """Approve all pending workflow runs.

        Returns:
            Tuple of (approved_count, failed_count)
        """
        pending = self.get_pending_runs()

        if not pending:
            logger.debug("No pending workflow runs")
            return 0, 0

        logger.info(f"Found {len(pending)} pending workflow run(s)")

        approved = 0
        failed = 0

        for run in pending:
            run_id = run.get("databaseId")
            if not run_id:
                continue
            workflow_name = run.get("workflowName", "Unknown")
            head_branch = run.get("headBranch", "unknown")

            display = f"'{workflow_name}' on {head_branch}"

            if self.approve_run(int(run_id), display):
                approved += 1
            else:
                failed += 1

        return approved, failed


def check_gh_auth() -> bool:
    """Check if gh CLI is authenticated."""
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        logger.error("gh CLI not found. Install from https://cli.github.com/")
        return False


def run_once(approver: WorkflowApprover) -> None:
    """Run approval check once."""
    approved, failed = approver.approve_all_pending()
    if approved > 0 or failed > 0:
        logger.info(f"Summary: {approved} approved, {failed} failed")


def run_daemon(approver: WorkflowApprover, interval: int) -> None:
    """Run approval checks continuously.

    Args:
        approver: The WorkflowApprover instance
        interval: Seconds between checks
    """
    logger.info(f"Starting daemon mode (interval={interval}s)")
    logger.info("Press Ctrl+C to stop")

    try:
        while True:
            run_once(approver)
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Stopped by user")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Auto-approve pending GitHub Actions workflow runs")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously instead of one-shot",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between checks in daemon mode (default: 60)",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"Repository in owner/repo format (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check gh CLI is available and authenticated
    if not check_gh_auth():
        logger.error("gh CLI not authenticated. Run: gh auth login")
        return 1

    approver = WorkflowApprover(repo=args.repo)

    logger.info(f"Checking pending workflows for {args.repo}")

    if args.daemon:
        run_daemon(approver, args.interval)
    else:
        run_once(approver)

    return 0


if __name__ == "__main__":
    sys.exit(main())
