#!/usr/bin/env python3
"""
Regression tests for merge routing and auto review dependency handling.

Tests dependency file counting, limited-scope detection, and draft handling.
"""

import pytest
from unittest.mock import patch
import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from merge_routing import count_dep_files, is_limited_scope, classify_pr
from auto_review_deps import (
    count_dep_files as auto_count_dep_files,
    is_limited_scope as auto_is_limited_scope,
    classify_pr as auto_classify_pr,
)


class TestDependencyFileHandling:
    """Test dependency file counting and scope detection."""

    def test_count_dep_files_dependency_only(self):
        """Test that count_dep_files only counts actual dependency files."""
        pr = {
            "files": [
                {"filename": "requirements.txt"},
                {"filename": "package.json"},
                {"filename": "frontend/package-lock.json"},
                {"filename": "src/main.py"},  # Non-dependency file
            ]
        }

        # Should count 3 dependency files, ignore src/main.py
        assert count_dep_files(pr) == 3
        assert auto_count_dep_files(pr) == 3

    def test_frontend_source_files_are_not_dependency_manifests(self):
        """Frontend source files must not be treated as dependency-only scope."""
        pr = {
            "files": [
                {"filename": "frontend/src/App.tsx"},
                {"filename": "frontend/package.json"},
                {"filename": "requirements.txt"},
            ]
        }

        assert count_dep_files(pr) == 2
        assert auto_count_dep_files(pr) == 2
        assert is_limited_scope(pr) is False
        assert auto_is_limited_scope(pr) is False

    def test_is_limited_scope_false_for_non_dependency(self):
        """Test that is_limited_scope returns False for any non-dependency path."""
        pr = {
            "files": [
                {"filename": "requirements.txt"},
                {"filename": "src/business_logic.py"},  # Non-dependency path
            ]
        }

        # Should be False because of src/business_logic.py
        assert is_limited_scope(pr) is False
        assert auto_is_limited_scope(pr) is False

    def test_is_limited_scope_true_for_dependency_only(self):
        """Test that is_limited_scope returns True when all files are dependency-related."""
        pr = {
            "files": [
                {"filename": "requirements.txt"},
                {"filename": "package.json"},
                {"filename": "frontend/package-lock.json"},
                {"filename": ".pre-commit-config.yaml"},
            ]
        }

        # Should be True - all files are dependency-related
        assert is_limited_scope(pr) is True
        assert auto_is_limited_scope(pr) is True


class TestDraftHandling:
    """Test draft PR handling."""

    @patch("merge_routing.check_ci_status")
    @patch("merge_routing.get_pr_age_days")
    @patch("merge_routing.count_dep_files")
    @patch("merge_routing.is_limited_scope")
    def test_draft_pr_never_auto_approve_merge_routing(self, mock_limited, mock_count, mock_age, mock_ci):
        """Test that draft PRs never get AUTO_APPROVE action in merge routing."""
        mock_ci.return_value = (True, {})
        mock_age.return_value = 1
        mock_count.return_value = 1
        mock_limited.return_value = True

        draft_pr = {"number": 123, "title": "Test PR", "isDraft": True, "mergeStateStatus": "CLEAN"}

        route = classify_pr(draft_pr, [])

        # Draft PRs should never have AUTO_APPROVE action
        assert route.action.value != "auto-approve"
        assert route.action.value == "comment"
        assert "draft" in route.reason.lower()

    @patch("auto_review_deps.check_ci_status")
    @patch("auto_review_deps.get_pr_age_days")
    @patch("auto_review_deps.count_dep_files")
    @patch("auto_review_deps.is_limited_scope")
    def test_draft_pr_explicit_handling_auto_review(self, mock_limited, mock_count, mock_age, mock_ci):
        """Test explicit draft handling in auto review."""
        mock_ci.return_value = (True, {})
        mock_age.return_value = 1
        mock_count.return_value = 1
        mock_limited.return_value = True

        draft_pr = {"number": 123, "title": "Test PR", "isDraft": True, "mergeStateStatus": "CLEAN"}

        classification = auto_classify_pr(draft_pr, [])

        # Draft PRs should be classified as tier 3 with comment action
        assert classification["tier"] == 3
        assert classification["action"] == "comment"
        assert "draft" in classification["reason"].lower()


class TestTierGating:
    """Test tier 1 gating by is_limited_scope."""

    @patch("merge_routing.check_ci_status")
    @patch("merge_routing.get_pr_age_days")
    @patch("merge_routing.count_dep_files")
    @patch("merge_routing.is_dependabot_pr")
    def test_tier1_gated_by_limited_scope(self, mock_is_dep, mock_count, mock_age, mock_ci):
        """Test that Tier 1 is gated by is_limited_scope."""
        mock_ci.return_value = (True, {})
        mock_age.return_value = 1  # < 7 days
        mock_count.return_value = 1  # <= 2 files
        mock_is_dep.return_value = True

        # PR with non-dependency files (limited_scope = False)
        non_limited_pr = {
            "number": 123,
            "title": "Test PR",
            "isDraft": False,
            "mergeStateStatus": "CLEAN",
            "files": [
                {"filename": "requirements.txt"},
                {"filename": "src/main.py"},  # Non-dependency file
            ],
        }

        route = classify_pr(non_limited_pr, [])

        # Should not be Tier 1 because scope is not limited
        assert route.tier.value != 1

        # PR with only dependency files (limited_scope = True)
        limited_pr = {
            "number": 124,
            "title": "Test PR 2",
            "isDraft": False,
            "mergeStateStatus": "CLEAN",
            "files": [{"filename": "requirements.txt"}],
        }

        route2 = classify_pr(limited_pr, [])

        # Should be Tier 1 because all conditions met including limited scope
        assert route2.tier.value == 1


if __name__ == "__main__":
    pytest.main([__file__])
