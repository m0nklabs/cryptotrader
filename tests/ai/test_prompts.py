"""Unit tests for the Prompt Registry.

Tests version management, default loading, DB backend, and cache invalidation.

Part of issue #209 (P6) for #205 Multi-Brain AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.ai.prompts.registry import PromptRegistry
from core.ai.types import RoleName, SystemPrompt


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset PromptRegistry before each test."""
    PromptRegistry._prompts.clear()
    PromptRegistry._db_enabled = False
    PromptRegistry._db_loaded = False
    PromptRegistry._activation_lock = None
    yield
    PromptRegistry._prompts.clear()
    PromptRegistry._db_enabled = False
    PromptRegistry._db_loaded = False
    PromptRegistry._activation_lock = None


# ---------------------------------------------------------------------------
# Default Loading Tests
# ---------------------------------------------------------------------------


def test_load_defaults():
    """Test loading default prompts from defaults.py module."""
    PromptRegistry.load_defaults()

    # Should have loaded all default prompts
    assert len(PromptRegistry._prompts) > 0

    # Check for specific defaults
    tactical_prompts = [p for p in PromptRegistry._prompts.values() if p.role == RoleName.TACTICAL]
    assert len(tactical_prompts) > 0

    # First default should be active
    tactical_v1 = [p for p in tactical_prompts if p.version == 1]
    assert len(tactical_v1) == 1
    assert tactical_v1[0].is_active


def test_load_defaults_all_roles():
    """Test that defaults include all role types."""
    PromptRegistry.load_defaults()

    roles_found = {p.role for p in PromptRegistry._prompts.values()}

    # Should have at least the main roles
    assert RoleName.SCREENER in roles_found
    assert RoleName.TACTICAL in roles_found
    assert RoleName.FUNDAMENTAL in roles_found
    assert RoleName.STRATEGIST in roles_found


def test_load_defaults_idempotent():
    """Test that loading defaults multiple times is safe."""
    PromptRegistry.load_defaults()
    count1 = len(PromptRegistry._prompts)

    PromptRegistry.load_defaults()
    count2 = len(PromptRegistry._prompts)

    # Should have same count (defaults don't duplicate)
    assert count1 == count2


# ---------------------------------------------------------------------------
# DB Backend Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_from_db_success(mock_db_session):
    """Test loading prompts from database."""
    # Mock DB prompts - use lowercase role names to match RoleName enum
    db_prompt1 = Mock()
    db_prompt1.id = "TACTICAL_v1"
    db_prompt1.role = "TACTICAL"  # Registry converts to RoleName
    db_prompt1.version = 1
    db_prompt1.content = "Test prompt content"
    db_prompt1.description = "Test prompt"
    db_prompt1.is_active = True
    db_prompt1.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    db_prompt2 = Mock()
    db_prompt2.id = "SCREENER_v1"
    db_prompt2.role = "SCREENER"
    db_prompt2.version = 1
    db_prompt2.content = "Screener prompt"
    db_prompt2.description = "Screener v1"
    db_prompt2.is_active = True
    db_prompt2.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with patch("db.crud.ai.get_prompts", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [db_prompt1, db_prompt2]

        await PromptRegistry.load_from_db(mock_db_session)

    # Check prompts were loaded
    assert len(PromptRegistry._prompts) == 2
    assert "TACTICAL_v1" in PromptRegistry._prompts
    assert "SCREENER_v1" in PromptRegistry._prompts
    assert PromptRegistry._db_enabled is True
    assert PromptRegistry._db_loaded is True


@pytest.mark.asyncio
async def test_load_from_db_empty_falls_back_to_defaults(mock_db_session):
    """Test that empty DB falls back to loading defaults."""
    with patch("db.crud.ai.get_prompts", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []  # Empty DB

        await PromptRegistry.load_from_db(mock_db_session)

    # Should have loaded defaults
    assert len(PromptRegistry._prompts) > 0
    assert PromptRegistry._db_enabled is True
    assert PromptRegistry._db_loaded is True


@pytest.mark.asyncio
async def test_load_from_db_error_falls_back_to_defaults(mock_db_session):
    """Test that DB error falls back to loading defaults."""
    with patch("db.crud.ai.get_prompts", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Database connection failed")

        await PromptRegistry.load_from_db(mock_db_session)

    # Should have loaded defaults despite error
    assert len(PromptRegistry._prompts) > 0
    assert PromptRegistry._db_enabled is False


@pytest.mark.asyncio
async def test_load_from_db_skips_invalid_roles(mock_db_session):
    """Test that prompts with invalid role names are skipped."""
    # Mock DB prompt with invalid role
    db_prompt_valid = Mock()
    db_prompt_valid.id = "TACTICAL_v1"
    db_prompt_valid.role = "TACTICAL"
    db_prompt_valid.version = 1
    db_prompt_valid.content = "Valid prompt"
    db_prompt_valid.description = "Valid"
    db_prompt_valid.is_active = True
    db_prompt_valid.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    db_prompt_invalid = Mock()
    db_prompt_invalid.id = "invalid_v1"
    db_prompt_invalid.role = "INVALID_ROLE"  # Not in RoleName enum
    db_prompt_invalid.version = 1
    db_prompt_invalid.content = "Invalid"
    db_prompt_invalid.description = "Invalid"
    db_prompt_invalid.is_active = True
    db_prompt_invalid.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with patch("db.crud.ai.get_prompts", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [db_prompt_valid, db_prompt_invalid]

        await PromptRegistry.load_from_db(mock_db_session)

    # Should only have the valid prompt
    assert len(PromptRegistry._prompts) == 1
    assert "TACTICAL_v1" in PromptRegistry._prompts
    assert "invalid_v1" not in PromptRegistry._prompts


# ---------------------------------------------------------------------------
# Get Active Prompt Tests
# ---------------------------------------------------------------------------


def test_get_active_prompt():
    """Test retrieving active prompt for a role."""
    PromptRegistry.load_defaults()

    prompt = PromptRegistry.get_active(RoleName.TACTICAL)

    assert prompt is not None
    assert prompt.role == RoleName.TACTICAL
    assert prompt.is_active


def test_get_active_no_active_prompt():
    """Test get_active when no active prompt exists for role."""
    # Load defaults but manually deactivate all tactical prompts
    PromptRegistry.load_defaults()
    for prompt_id, prompt in PromptRegistry._prompts.items():
        if prompt.role == RoleName.TACTICAL:
            # Create new prompt with is_active=False
            PromptRegistry._prompts[prompt_id] = SystemPrompt(
                id=prompt.id,
                role=prompt.role,
                version=prompt.version,
                content=prompt.content,
                description=prompt.description,
                is_active=False,
                created_at=prompt.created_at,
            )

    # get_active returns None when no active prompt exists
    result = PromptRegistry.get_active(RoleName.TACTICAL)
    assert result is None


def test_get_active_multiple_versions_returns_active():
    """Test that get_active returns the active version when multiple exist."""
    # Add multiple versions, only one active
    prompt_v1 = SystemPrompt(
        id="tactical_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="Version 1",
        description="V1",
        is_active=False,  # Inactive
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    prompt_v2 = SystemPrompt(
        id="tactical_v2",
        role=RoleName.TACTICAL,
        version=2,
        content="Version 2",
        description="V2",
        is_active=True,  # Active
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    PromptRegistry._prompts["tactical_v1"] = prompt_v1
    PromptRegistry._prompts["tactical_v2"] = prompt_v2

    active = PromptRegistry.get_active(RoleName.TACTICAL)

    assert active.version == 2
    assert active.id == "tactical_v2"


# ---------------------------------------------------------------------------
# Version Management Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_prompt_version(mock_db_session):
    """Test creating a new prompt version using create_prompt."""
    PromptRegistry._db_enabled = True

    with patch("db.crud.ai.create_prompt", new_callable=AsyncMock) as mock_create:
        with patch("db.crud.ai.get_next_version", new_callable=AsyncMock) as mock_next_version:
            # Mock getting next version
            mock_next_version.return_value = 2

            # Mock DB create
            db_prompt = Mock()
            db_prompt.id = "TACTICAL_v2"
            db_prompt.role = "TACTICAL"
            db_prompt.version = 2
            db_prompt.content = "New version"
            db_prompt.description = "V2 test"
            db_prompt.is_active = True
            db_prompt.created_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
            mock_create.return_value = db_prompt

            new_prompt = await PromptRegistry.create_prompt(
                db=mock_db_session,
                role=RoleName.TACTICAL,
                content="New version",
                description="V2 test",
            )

    # Check it was added to cache
    assert "TACTICAL_v2" in PromptRegistry._prompts
    assert new_prompt.version == 2


@pytest.mark.asyncio
async def test_create_prompt_db_disabled_raises(mock_db_session):
    """Test that creating prompt fails when DB is disabled."""
    PromptRegistry._db_enabled = False

    with pytest.raises(RuntimeError, match="DB backend is not enabled"):
        await PromptRegistry.create_prompt(
            db=mock_db_session,
            role=RoleName.TACTICAL,
            content="Test",
            description="Test",
        )


@pytest.mark.asyncio
async def test_activate_prompt_by_id(mock_db_session):
    """Test activating a specific prompt using activate_prompt."""
    PromptRegistry._db_enabled = True

    # Add two versions
    prompt_v1 = SystemPrompt(
        id="TACTICAL_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="V1",
        description="V1",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    prompt_v2 = SystemPrompt(
        id="TACTICAL_v2",
        role=RoleName.TACTICAL,
        version=2,
        content="V2",
        description="V2",
        is_active=False,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    PromptRegistry._prompts["TACTICAL_v1"] = prompt_v1
    PromptRegistry._prompts["TACTICAL_v2"] = prompt_v2

    with patch("db.crud.ai.activate_prompt", new_callable=AsyncMock) as mock_activate:
        # Mock DB response
        db_prompt = Mock()
        db_prompt.id = "TACTICAL_v2"
        db_prompt.role = "TACTICAL"
        db_prompt.version = 2
        db_prompt.content = "V2"
        db_prompt.description = "V2"
        db_prompt.is_active = True
        db_prompt.created_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
        mock_activate.return_value = db_prompt

        await PromptRegistry.activate_prompt(
            db=mock_db_session,
            prompt_id="TACTICAL_v2",
        )

    # Check v2 is now active and v1 is inactive
    assert PromptRegistry._prompts["TACTICAL_v2"].is_active is True
    assert PromptRegistry._prompts["TACTICAL_v1"].is_active is False


@pytest.mark.asyncio
async def test_activate_nonexistent_prompt_returns_none(mock_db_session):
    """Test activating a non-existent prompt returns None."""
    PromptRegistry._db_enabled = True

    with patch("db.crud.ai.activate_prompt", new_callable=AsyncMock) as mock_activate:
        mock_activate.return_value = None  # Not found

        result = await PromptRegistry.activate_prompt(
            db=mock_db_session,
            prompt_id="nonexistent_v999",
        )

        assert result is None


# Skip test - deactivate_all method doesn't exist in PromptRegistry
# Use activate_prompt to change active prompts instead
@pytest.mark.skip(reason="deactivate_all method not in PromptRegistry API")
@pytest.mark.asyncio
async def test_deactivate_all_for_role(mock_db_session):
    """Test deactivating all prompts for a role."""
    pass


# ---------------------------------------------------------------------------
# List Prompts Tests
# ---------------------------------------------------------------------------


def test_list_versions_for_role():
    """Test listing all prompt versions for a specific role using list_versions."""
    # Add multiple versions
    prompt_v1 = SystemPrompt(
        id="TACTICAL_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="V1",
        description="V1",
        is_active=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    prompt_v2 = SystemPrompt(
        id="TACTICAL_v2",
        role=RoleName.TACTICAL,
        version=2,
        content="V2",
        description="V2",
        is_active=True,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    prompt_other = SystemPrompt(
        id="SCREENER_v1",
        role=RoleName.SCREENER,
        version=1,
        content="Other",
        description="Other",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    PromptRegistry._prompts["TACTICAL_v1"] = prompt_v1
    PromptRegistry._prompts["TACTICAL_v2"] = prompt_v2
    PromptRegistry._prompts["SCREENER_v1"] = prompt_other

    tactical_prompts = PromptRegistry.list_versions(RoleName.TACTICAL)

    assert len(tactical_prompts) == 2
    assert all(p.role == RoleName.TACTICAL for p in tactical_prompts)


# Skip - list_prompts method doesn't exist, use list_versions instead
@pytest.mark.skip(reason="list_prompts without arg doesn't exist, testing list_versions elsewhere")
def test_list_prompts_all_roles():
    pass


def test_list_versions_sorted_by_version():
    """Test that prompts are sorted by version."""
    # Add versions out of order
    prompt_v3 = SystemPrompt(
        id="tactical_v3",
        role=RoleName.TACTICAL,
        version=3,
        content="V3",
        description="V3",
        is_active=True,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    prompt_v1 = SystemPrompt(
        id="tactical_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="V1",
        description="V1",
        is_active=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    prompt_v2 = SystemPrompt(
        id="tactical_v2",
        role=RoleName.TACTICAL,
        version=2,
        content="V2",
        description="V2",
        is_active=False,
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    PromptRegistry._prompts["tactical_v3"] = prompt_v3
    PromptRegistry._prompts["tactical_v1"] = prompt_v1
    PromptRegistry._prompts["tactical_v2"] = prompt_v2

    prompts = PromptRegistry.list_versions(RoleName.TACTICAL)

    # Should be sorted by version descending (newest first)
    versions = [p.version for p in prompts]
    assert versions == [3, 2, 1]


# ---------------------------------------------------------------------------
# Cache Invalidation Tests
# ---------------------------------------------------------------------------


def test_clear_registry():
    """Test clearing the prompt registry using clear()."""
    PromptRegistry.load_defaults()
    assert len(PromptRegistry._prompts) > 0

    PromptRegistry.clear()

    assert len(PromptRegistry._prompts) == 0


# Skip - reload_from_db doesn't exist, use load_from_db instead
@pytest.mark.skip(reason="reload_from_db method doesn't exist")
@pytest.mark.asyncio
async def test_reload_from_db(mock_db_session):
    pass


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


def test_duplicate_prompt_id_last_write_wins():
    """Test handling of duplicate prompt IDs (last write wins)."""
    prompt_v1a = SystemPrompt(
        id="TACTICAL_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="First",
        description="First",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    prompt_v1b = SystemPrompt(
        id="TACTICAL_v1",  # Same ID
        role=RoleName.TACTICAL,
        version=1,
        content="Second",
        description="Second",
        is_active=True,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    PromptRegistry._prompts["TACTICAL_v1"] = prompt_v1a
    PromptRegistry._prompts["TACTICAL_v1"] = prompt_v1b  # Overwrite

    # Last write wins
    assert PromptRegistry._prompts["TACTICAL_v1"].content == "Second"


def test_get_by_id():
    """Test retrieving prompt by exact ID using get()."""
    prompt = SystemPrompt(
        id="TACTICAL_v1",
        role=RoleName.TACTICAL,
        version=1,
        content="Test",
        description="Test",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    PromptRegistry._prompts["TACTICAL_v1"] = prompt

    retrieved = PromptRegistry.get("TACTICAL_v1")

    assert retrieved is not None
    assert retrieved.id == "TACTICAL_v1"


def test_get_by_id_not_found():
    """Test get() returns None for missing prompt."""
    retrieved = PromptRegistry.get("nonexistent")

    assert retrieved is None
