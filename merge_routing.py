#!/usr/bin/env python3
"""Dependency PR Merge Routing for cryptotrader_hermes.

Scans open PRs, classifies them into merge tiers, and optionally
auto-approves / merges them.

Tier 1 (Manual-ready):     PRs that are ready but need a human to click merge.
Tier 2 (Auto-Approve):    PRs that can be auto-approved and merged.
Tier 3 (Manual):           PRs that need manual review before merging.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    TIER1 = "Tier 1 (Manual-ready)"
    TIER2 = "Tier 2 (Auto-Approve)"
    TIER3 = "Tier 3 (Manual)"


@dataclass
class PRInfo:
    number: int
    title: str
    url: str
    author: str
    labels: list[str]
    tier: Tier
    reason: str
    draft: bool = False
    base_branch: str = "main"


# ---------------------------------------------------------------------------
# GitHub helper
# ---------------------------------------------------------------------------

def run_gh(args: list[str], **kwargs: Any) -> str:
    """Run a gh CLI command and return stdout."""
    cmd = ["gh"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0 and not kwargs.get("check", True):
        return ""
    return result.stdout.strip()


def list_open_prs(repo: str = "cryptotrader_hermes") -> list[dict]:
    """Return a list of open PR dicts from gh pr list."""
    output = run_gh(
        [
            "pr", "list",
            "--state", "open",
            "--json", "number,title,url,author,labels,draft,baseRefName",
            "--limit", "100",
        ],
        check=False,
    )
    if not output:
        return []
    return json.loads(output)


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------

def classify_pr(pr: dict) -> PRInfo:
    """Classify a single PR into a merge tier."""
    number = pr["number"]
    title = pr["title"]
    url = pr["url"]
    author = pr["author"]["login"] if isinstance(pr["author"], dict) else str(pr["author"])
    labels = [
        lbl["name"] if isinstance(lbl, dict) else lbl
        for lbl in pr.get("labels", [])
    ]
    draft = pr.get("draft", False)
    base_branch = pr.get("baseRefName", "main")

    label_set = {lbl.lower() for lbl in labels}
    title_lower = title.lower()

    # Auto-approve conditions (Tier 2)
    auto_approve_patterns = [
        "dependency", "deps", "bump", "update", "chore",
    ]
    is_dependency = any(p in title_lower or p in " ".join(labels) for p in auto_approve_patterns)

    # Small, dependency PRs from dependabot or with no conflicts → Tier 2
    if is_dependency and "conflict" not in " ".join(labels).lower():
        # Check if it's from dependabot or similar automation
        if "dependabot" in author.lower() or "depend" in author.lower():
            return PRInfo(
                number=number, title=title, url=url, author=author,
                labels=labels, tier=Tier.TIER2,
                reason="Dependency PR from automated bot, no conflicts",
                draft=draft, base_branch=base_branch,
            )
        return PRInfo(
            number=number, title=title, url=url, author=author,
            labels=labels, tier=Tier.TIER2,
            reason="Dependency PR, no conflicts",
            draft=draft, base_branch=base_branch,
        )

    # Manual-ready: has labels indicating readiness
    ready_patterns = ["ready", "approved", "lgtm", "ci-passing"]
    if any(p in " ".join(labels).lower() for p in ready_patterns):
        return PRInfo(
            number=number, title=title, url=url, author=author,
            labels=labels, tier=Tier.TIER1,
            reason="PR marked as ready for merge",
            draft=draft, base_branch=base_branch,
        )

    # Default: Tier 3 (Manual)
    return PRInfo(
        number=number, title=title, url=url, author=author,
        labels=labels, tier=Tier.TIER3,
        reason="Requires manual review",
        draft=draft, base_branch=base_branch,
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def auto_approve(pr: PRInfo, dry_run: bool = True) -> None:
    """Auto-approve a PR via gh."""
    if dry_run:
        print(f"  [DRY-RUN] gh pr review --approve #{pr.number}")
    else:
        run_gh(["pr", "review", "--approve", f"#{pr.number}"])
        print(f"  Auto-approved #{pr.number}")


def auto_merge(pr: PRInfo, dry_run: bool = True) -> None:
    """Auto-merge a PR via gh."""
    if dry_run:
        print(f"  [DRY-RUN] gh pr merge --squash #{pr.number}")
    else:
        run_gh(["pr", "merge", "--squash", f"#{pr.number}"])
        print(f"  Merged #{pr.number}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Dependency PR Merge Routing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show actions without executing")
    parser.add_argument("--auto-merge", action="store_true", help="Auto-merge Tier 2 PRs")
    parser.add_argument("--repo", default="cryptotrader_hermes", help="GitHub repo name")
    args = parser.parse_args()

    print("=" * 60)
    print("Dependency PR Merge Routing")
    print("=" * 60)

    # Fetch open PRs
    prs = list_open_prs(args.repo)
    print(f"\nFound {len(prs)} open PRs\n")

    # Classify each PR
    classified: list[PRInfo] = []
    for pr in prs:
        info = classify_pr(pr)
        classified.append(info)
        if args.verbose:
            print(f"  #{info.number}: {info.title}")
            print(f"    → {info.tier.value}  ({info.reason})")

    # Routing summary
    print("\nRouting summary:")
    for tier in [Tier.TIER1, Tier.TIER2, Tier.TIER3]:
        count = sum(1 for p in classified if p.tier == tier)
        print(f"  {tier.value}: {count}")

    # Execute routes
    print("\n" + "=" * 60)
    print("Executing routes:")
    print("=" * 60)

    for info in classified:
        if info.tier == Tier.TIER2 and args.auto_merge:
            auto_merge(info, dry_run=args.dry_run)
        elif info.tier == Tier.TIER2:
            auto_approve(info, dry_run=args.dry_run)
        elif info.tier == Tier.TIER1:
            if args.verbose:
                print(f"  #{info.number}: {info.title} → {info.tier.value} (manual-ready)")
        else:
            if args.verbose:
                print(f"  #{info.number}: {info.title} → {info.tier.value} (needs review)")

    # Results
    print("\n" + "=" * 60)
    print("Results:")
    print("=" * 60)

    tier_dist: dict[str, int] = {}
    for tier in [Tier.TIER1, Tier.TIER2, Tier.TIER3]:
        label = tier.value
        tier_dist[label] = sum(1 for p in classified if p.tier == tier)

    for label, count in tier_dist.items():
        print(f"\n  {label}: {count}")

    print("\n[Merge routing complete]")


if __name__ == "__main__":
    main()
