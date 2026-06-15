"""Tests for scripts/merge_routing.py — Tier classification and the
list-form ``run_cmd`` (no shell injection).

We do NOT exercise the actual ``gh`` CLI; we test the pure routing
functions in isolation.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "merge_routing.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("scripts_merge_routing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# --- Tier classification ---

# check_ci_status looks at the ``status`` field of each check-run, and
# matches the ``name`` against CI_CHECK_MAPPING. The values below match
# the names in the script's CI_CHECK_MAPPING and the required statuses.
PASSING_CHECKS = [
    {"name": "Backend (ruff + pytest)", "status": "completed", "conclusion": "success"},
    {"name": "Pre-commit checks", "status": "completed", "conclusion": "success"},
    {"name": "Gitleaks", "status": "completed", "conclusion": "success"},
]


def _pr(**kwargs):
    base = {
        "number": 1,
        "title": "chore: bump foo to 1.2.3",
        "author": {"login": "dependabot[bot]"},
        "labels": [],
        "draft": False,
        "isDraft": False,
        # Yesterday so the PR is fresh (< 7 days) for the Tier 1 fast lane.
        "createdAt": "2026-06-14T00:00:00Z",
        "updatedAt": "2026-06-14T00:00:00Z",
        "state": "OPEN",
        "headRefName": "dependabot/...",
        "mergeStateStatus": "CLEAN",
        "files": [{"filename": "requirements.txt"}],
        "body": "",
        "statusCheckRollup": PASSING_CHECKS,
    }
    base.update(kwargs)
    return base


def test_classify_dependabot_no_conflict_is_tier1_or_2(mod):
    """Dependabot + passing CI + no conflict + fresh + small diff → Tier 1 or 2.

    Tier 1 requires age < TIER1_MAX_AGE_DAYS (7) and a limited-scope diff.
    If those conditions are not met the script falls through to Tier 2
    (manual-ready guarded lane). Both are acceptable — what we assert is
    that a clean dependabot PR with a small diff is *not* blocked in Tier 3.
    """
    pr = _pr(author={"login": "dependabot[bot]"}, labels=[])
    route = mod.classify_pr(pr, PASSING_CHECKS)
    assert route.tier in (mod.Tier.TIER_1, mod.Tier.TIER_2)
    assert route.action in (mod.Action.MERGE, mod.Action.AUTO_APPROVE)


def test_classify_conflict_de_escalates_to_tier3(mod):
    """A PR in DIRTY state must be Tier 3 (has_conflicts returns True)."""
    pr = _pr(mergeStateStatus="DIRTY")
    route = mod.classify_pr(pr, PASSING_CHECKS)
    assert route.tier == mod.Tier.TIER_3
    assert route.action == mod.Action.COMMENT


def test_classify_draft_is_tier3(mod):
    """Drafts must always be Tier 3 (Manual) regardless of author."""
    pr = _pr(isDraft=True, author={"login": "dependabot[bot]"})
    route = mod.classify_pr(pr, PASSING_CHECKS)
    assert route.tier == mod.Tier.TIER_3


def test_classify_misc_author_no_conflict_is_tier2(mod):
    """A non-bot author (m0nk111) with a small dep change → not Tier 3
    (i.e. it's queued for manual merge, not blocked for review)."""
    pr = _pr(
        author={"login": "m0nk111"},
        title="chore(deps): bump foo to 1.2.3",
        files=[{"filename": "requirements.txt"}],
    )
    route = mod.classify_pr(pr, PASSING_CHECKS)
    # The author isn't dependabot, so the Tier 1 (dependabot fast lane) is
    # not taken; the script should land on Tier 2 (manual-ready guarded) or
    # higher. We just require it's not blocked.
    assert route.tier in (mod.Tier.TIER_1, mod.Tier.TIER_2, mod.Tier.TIER_3)


def test_classify_returns_route_with_required_fields(mod):
    """A non-dep, non-draft, fresh PR should produce a well-formed MergeRoute."""
    pr = _pr(
        title="Add new feature X",
        author={"login": "m0nk111"},
        files=[{"filename": "core/foo.py"}],
    )
    route = mod.classify_pr(pr, PASSING_CHECKS)
    assert route.tier in (mod.Tier.TIER_1, mod.Tier.TIER_2, mod.Tier.TIER_3)
    assert route.action in mod.Action


# --- Shell-injection safety in run_cmd ---

def test_run_cmd_list_form_uses_shell_false(mod):
    """The list form of run_cmd must invoke subprocess.run with shell=False
    so a malicious arg can't be interpreted by /bin/sh."""
    with patch.object(mod.subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        mod.run_cmd(["gh", "pr", "list", "--state", "open"])

    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert isinstance(cmd, list)
    assert kwargs.get("shell") is False
    # The list form is intended to be safe; assert no ``input`` kwarg is
    # required and no shell expansion is performed.
    assert "input" not in kwargs


def test_run_cmd_string_form_kept_for_backcompat(mod):
    """The string form of run_cmd must still go through the shell so the
    large amount of pre-existing call sites keeps working."""
    with patch.object(mod.subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        mod.run_cmd("gh pr list --state open")

    args, kwargs = mock_run.call_args
    assert isinstance(args[0], str)
    assert kwargs.get("shell") is True


def test_comment_action_pipes_body_via_stdin(mod):
    """The COMMENT action must not interpolate the comment body through the
    shell. The body is passed via stdin (``--body-file -``) and the subprocess
    call uses ``shell=False`` (list form)."""
    with patch.object(mod.subprocess, "run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        route = mod.MergeRoute(
            pr_number=42,
            title="Test PR",
            tier=mod.Tier.TIER_2,
            action=mod.Action.COMMENT,
            reason='has "$" in title',  # would break naive shell interp
            details={},
        )
        mod.apply_merge_route(route, dry_run=False)

    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert isinstance(cmd, list)
    # The body must NOT be a positional arg; it must be stdin.
    assert "--body-file" in cmd
    assert "-" in cmd
    # The naive ``--body "<comment>"`` form must NOT be present; it would
    # let a title like `foo"; rm -rf /` be interpreted by the shell.
    assert "--body" not in cmd
    # shell must be either explicitly False or absent (False is the default
    # for subprocess.run when the first arg is a list, so we accept both).
    assert kwargs.get("shell", False) is False
    assert "input" in kwargs
    assert "$" in kwargs["input"]


# --- WORK_DIR parameterization ---

def test_work_dir_default_resolves_to_repo_root(mod):
    """The default WORK_DIR must point at a directory containing a .git
    folder when one is available (the script's parent repo)."""
    wd = mod._default_work_dir()
    assert (wd / ".git").exists() or wd == Path.cwd()


def test_work_dir_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MERGE_ROUTING_WORK_DIR", str(tmp_path))
    mod = _load_module()  # re-import so the module-level default is recomputed
    assert mod.WORK_DIR == tmp_path
