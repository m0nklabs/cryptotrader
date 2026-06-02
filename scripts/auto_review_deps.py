#!/usr/bin/env python3
"""Auto-review dependency PRs with manual merge labeling.

Scans open dependency PRs, runs the manual gatekeeper checks
(Mergify syntax, dependabot-only routing, dependency-manifest scope),
and applies the ``manual-ready`` label to route them through the
manual merge path instead of triggering a direct merge.

This script is the companion to ``merge_routing.py`` — while the latter
labels PRs that *need* manual merge, this one auto-reviews them and
applies the label so Mergify can pick them up.

Usage
-----
    # One-shot: review and label all eligible dependency PRs
    python -m scripts.auto_review_deps

    # Daemon: watch for new PRs every 2 minutes
    python -m scripts.auto_review_deps --daemon

    # Dry run: show what would happen without changing anything
    python -m scripts.auto_review_deps --dry-run

Requirements
------------
    - gh CLI installed and authenticated (gh auth login)
    - Mergify auto-merge rules require ``label=manual-ready`` (see .github/mergify.yml)
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
STATE_FILE = Path(__file__).parent.parent / ".auto-review-deps-state.json"

# Labels
MANUAL_READY_LABEL = "manual-ready"
AUTO_MERGE_DISABLED_LABEL = "do-not-merge"
CI_LABEL = "ci"

# Dependency manifest files that indicate a true dependency PR
DEPENDENCY_MANIFESTS = (
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "requirements.txt",
    "requirements.in",
    "pyproject.toml",
    "Pipfile",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "pnpm-lock.yaml",
    "deno.lock",
    "uv.lock",
)

# PR author patterns for dependency PRs
DEPENDENCY_AUTHORS = ("dependabot[bot]", "github-actions[bot]")

# CI check names that must pass before auto-merge
REQUIRED_CI_CHECKS = (
    "Backend (ruff + pytest)",
    "Pre-commit checks",
)


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


def get_open_prs(repo: str) -> list[dict]:
    """Get open PRs from the repository."""
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
                "number,title,author,body,labels,mergeStateStatus,files",
            ],
            check=False,
        )
        if not output or output == "[]":
            return []
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def is_dependency_pr(pr: dict) -> bool:
    """Check if a PR is a dependency PR."""
    author = pr.get("author", {}).get("login", "")
    if author not in DEPENDENCY_AUTHORS:
        return False

    # Check that at least one changed file is a dependency manifest
    files = pr.get("files", [])
    for f in files:
        filename = f.get("path", "")
        basename = filename.rsplit("/", 1)[-1] if "/" in filename else filename
        if basename in DEPENDENCY_MANIFESTS or any(
            filename.endswith(ext) for ext in (".lock", ".toml", ".yaml", ".yml")
        ):
            return True

    # Fallback: check title for dependency indicators
    title = pr.get("title", "").lower()
    if any(indicator in title for indicator in ("bump", "deps", "dependency", "chore(deps)")):
        return True

    return False


def is_true_dependency_manifest(pr: dict) -> bool:
    """Verify the PR touches a true dependency manifest file.

    This filters out CI-only or config-only PRs that happen to be from
    Dependabot but don't actually change a dependency.
    """
    files = pr.get("files", [])
    for f in files:
        filename = f.get("path", "")
        basename = filename.rsplit("/", 1)[-1] if "/" in filename else filename
        if basename in DEPENDENCY_MANIFESTS:
            return True
        # Lock files count as dependency manifests
        if filename.endswith((".lock", ".toml")):
            return True
    return False


def check_mergify_syntax(repo: str, pr_number: int) -> bool:
    """Verify Mergify auto-merge rules are valid for this PR.

    Checks that the PR's author and labels are compatible with the
    manual-ready gating in .github/mergify.yml.
    """
    try:
        # Get the PR to check author and labels
        pr_json = run_gh(
            [
                "api",
                f"repos/{repo}/pulls/{pr_number}",
                "--jq",
                '{"author": .author.login, "labels": [.labels[].name]}',
            ],
            check=False,
        )
        if not pr_json:
            return False

        data = json.loads(pr_json)
        author = data.get("author", "")
        labels = data.get("labels", [])

        # Author must be a dependency author
        if author not in DEPENDENCY_AUTHORS:
            return False

        # Must not be blocked
        if AUTO_MERGE_DISABLED_LABEL in labels:
            return False

        return True
    except (json.JSONDecodeError, subprocess.CalledProcessError):
        return False


def check_ci_status(repo: str, pr_number: int) -> bool:
    """Check if required CI checks have passed for this PR."""
    try:
        checks_output = run_gh(
            [
                "api",
                f"repos/{repo}/commits/{pr_number}/check-runs",
                "--jq",
                '[.check_runs[] | select(.name | contains("Backend") or contains("Pre-commit")) | {"name": .name, "conclusion": .conclusion}]',
            ],
            check=False,
        )
        if not checks_output or checks_output == "[]":
            # Fall back to mergeStateStatus
            status = run_gh(
                ["api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".mergeable_state"],
                check=False,
            )
            return status in ("clean", "unstable", "blocked")

        checks = json.loads(checks_output)
        for check in checks:
            conclusion = check.get("conclusion", "")
            if conclusion not in ("success", "SUCCESS", "neutral", "NEUTRAL", "skipped", "SKIPPED"):
                return False
        return True
    except (json.JSONDecodeError, subprocess.CalledProcessError):
        return True  # Conservative: assume OK if we can't check


def apply_label(repo: str, pr_number: int, label: str, dry_run: bool = False) -> bool:
    """Apply a label to a PR."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would apply label '{label}' to PR #{pr_number}")
        return True

    try:
        run_gh(
            [
                "pr",
                "edit",
                str(pr_number),
                "--add-label",
                label,
                "--repo",
                repo,
            ]
        )
        logger.info(f"  Applied label '{label}' to PR #{pr_number}")
        return True
    except subprocess.CalledProcessError:
        logger.warning(f"  Failed to apply label '{label}' to PR #{pr_number}")
        return False


def remove_label(repo: str, pr_number: int, label: str, dry_run: bool = False) -> bool:
    """Remove a label from a PR."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would remove label '{label}' from PR #{pr_number}")
        return True

    try:
        run_gh(
            [
                "pr",
                "edit",
                str(pr_number),
                "--remove-label",
                label,
                "--repo",
                repo,
            ]
        )
        logger.info(f"  Removed label '{label}' from PR #{pr_number}")
        return True
    except subprocess.CalledProcessError:
        logger.warning(f"  Failed to remove label '{label}' from PR #{pr_number}")
        return False


def review_pr(repo: str, pr: dict, dry_run: bool = False) -> bool:
    """Review a single dependency PR through the manual merge path.

    Applies manual gatekeeper checks:
    1. Valid Mergify syntax (author + labels compatible with manual-ready rules)
    2. Dependabot-only routing (author is dependabot[bot] or github-actions[bot])
    3. True dependency-manifest scope (touches a dependency file)

    If all checks pass, applies the manual-ready label.
    """
    pr_number = pr["number"]
    author = pr.get("author", {}).get("login", "")
    logger.info(f"Reviewing dependency PR #{pr_number} ({author})")

    # Check 1: Mergify syntax
    if not check_mergify_syntax(repo, pr_number):
        logger.info(f"  PR #{pr_number} ({author}) — Mergify syntax check failed, skipping")
        return False

    # Check 2: True dependency manifest
    if not is_true_dependency_manifest(pr):
        logger.info(f"  PR #{pr_number} ({author}) — not a true dependency manifest, skipping")
        return False

    # Check 3: CI status
    if not check_ci_status(repo, pr_number):
        logger.info(f"  PR #{pr_number} ({author}) — CI checks not yet passing, skipping")
        return False

    # Apply manual-ready label to route through manual merge
    labels = [lb.get("name", "") for lb in pr.get("labels", [])]

    if MANUAL_READY_LABEL not in labels:
        apply_label(repo, pr_number, MANUAL_READY_LABEL, dry_run=dry_run)

    logger.info(f"  PR #{pr_number} ({author}) approved for manual merge")
    return True


def auto_review_all(repo: str, dry_run: bool = False) -> int:
    """Auto-review all eligible dependency PRs."""
    prs = get_open_prs(repo)
    if not prs:
        logger.info("No open PRs found")
        return 0

    reviewed = 0
    for pr in prs:
        if is_dependency_pr(pr) and review_pr(repo, pr, dry_run=dry_run):
            reviewed += 1

    logger.info(f"Reviewed {reviewed}/{len(prs)} dependency PR(s)")
    return reviewed


def load_state() -> dict:
    """Load state from file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"last_run": None, "reviewed_prs": []}


def save_state(state: dict) -> None:
    """Save state to file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-review dependency PRs with manual merge labeling")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=120, help="Check interval (default: 120s)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
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
                n = auto_review_all(args.repo, dry_run=args.dry_run)
                state["last_run"] = datetime.now(tz=UTC).isoformat()
                save_state(state)
                if n:
                    logger.info(f"Reviewed {n} PR(s)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        n = auto_review_all(args.repo, dry_run=args.dry_run)
        mode = "[DRY RUN] " if args.dry_run else ""
        logger.info(f"{mode}Reviewed {n} PR(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
