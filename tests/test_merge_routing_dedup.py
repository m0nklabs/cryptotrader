"""Tests for merge_routing deduplication and state management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module functions directly
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from merge_routing import (
    deduplicate_processed_prs,
    clean_state,
    PROCESSED_PRS_MAX_SIZE,
)


class TestDeduplicateProcessedPrs:
    """Tests for deduplicate_processed_prs function."""

    def test_basic_deduplication(self):
        """Test that duplicates are removed."""
        state = {"processed_prs": ["pr_257", "pr_259", "pr_261", "pr_263", "pr_264"] * 10}
        result = deduplicate_processed_prs(state)
        assert len(result["processed_prs"]) == 5
        assert result["processed_prs"] == ["pr_257", "pr_259", "pr_261", "pr_263", "pr_264"]

    def test_preserves_order(self):
        """Test that insertion order is preserved."""
        state = {"processed_prs": ["pr_264", "pr_261", "pr_257", "pr_264", "pr_259"]}
        result = deduplicate_processed_prs(state)
        assert result["processed_prs"] == ["pr_264", "pr_261", "pr_257", "pr_259"]

    def test_lru_eviction(self):
        """Test that LRU eviction keeps most recent entries when over max size."""
        # Create a list larger than max size
        large_list = [f"pr_{i}" for i in range(100)]
        state = {"processed_prs": large_list}
        result = deduplicate_processed_prs(state)
        assert len(result["processed_prs"]) <= PROCESSED_PRS_MAX_SIZE
        # Should keep the last N entries
        assert result["processed_prs"] == large_list[-PROCESSED_PRS_MAX_SIZE:]

    def test_empty_list(self):
        """Test with empty processed_prs."""
        state = {"processed_prs": []}
        result = deduplicate_processed_prs(state)
        assert result["processed_prs"] == []

    def test_no_duplicates(self):
        """Test with no duplicates."""
        state = {"processed_prs": ["pr_257", "pr_259", "pr_261"]}
        result = deduplicate_processed_prs(state)
        assert result["processed_prs"] == ["pr_257", "pr_259", "pr_261"]

    def test_sets_dedup_at_timestamp(self):
        """Test that dedup_at timestamp is set."""
        state = {"processed_prs": ["pr_257", "pr_257"]}
        result = deduplicate_processed_prs(state)
        assert "dedup_at" in result


class TestCleanState:
    """Tests for clean_state function."""

    def test_truncates_processed_prs(self):
        """Test that processed_prs is truncated when too large."""
        large_list = [f"pr_{i}" for i in range(200)]
        state = {"processed_prs": large_list, "rerun_runs": list(range(100))}
        result = clean_state(state)
        assert len(result["processed_prs"]) <= PROCESSED_PRS_MAX_SIZE

    def test_truncates_rerun_runs(self):
        """Test that rerun_runs is truncated when too large."""
        large_reruns = list(range(1000))
        state = {"processed_prs": ["pr_257"], "rerun_runs": large_reruns}
        result = clean_state(state)
        assert len(result["rerun_runs"]) == 500

    def test_no_truncation_needed(self):
        """Test that lists within limits are not modified."""
        state = {"processed_prs": ["pr_257"], "rerun_runs": list(range(100))}
        result = clean_state(state)
        assert len(result["processed_prs"]) == 1
        assert len(result["rerun_runs"]) == 100
