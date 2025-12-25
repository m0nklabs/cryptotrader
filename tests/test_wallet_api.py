"""Tests for wallet balances API endpoint."""

from __future__ import annotations

import os
from unittest.mock import patch


def test_fetch_wallet_balances_paper_mode():
    """Test that wallet endpoint returns mock balances when API keys are not configured."""
    # Ensure no API keys are set
    with patch.dict(os.environ, {}, clear=True):
        from scripts.api_server import _fetch_wallet_balances
        
        wallets = _fetch_wallet_balances()
        
        assert isinstance(wallets, list)
        assert len(wallets) >= 3
        
        # Check mock data structure
        for wallet in wallets:
            assert "type" in wallet
            assert "currency" in wallet
            assert "balance" in wallet
            assert "available" in wallet
            assert isinstance(wallet["balance"], float)
            assert isinstance(wallet["available"], float)
        
        # Check specific mock balances
        usd_wallet = next((w for w in wallets if w["currency"] == "USD" and w["type"] == "exchange"), None)
        assert usd_wallet is not None
        assert usd_wallet["balance"] == 10000.0
        assert usd_wallet["available"] == 10000.0
        
        btc_wallet = next((w for w in wallets if w["currency"] == "BTC"), None)
        assert btc_wallet is not None
        assert btc_wallet["balance"] == 0.5


def test_fetch_wallet_balances_structure():
    """Test that wallet response has the correct structure."""
    # Clear env to force paper mode (mock data)
    with patch.dict(os.environ, {}, clear=True):
        from importlib import reload
        import scripts.api_server as api_server_mod
        reload(api_server_mod)
        from scripts.api_server import _fetch_wallet_balances
        
        wallets = _fetch_wallet_balances()
    
        assert isinstance(wallets, list)
        
        for wallet in wallets:
            assert "type" in wallet
            assert "currency" in wallet
            assert "balance" in wallet
            assert "available" in wallet
            
            # Validate types
            assert isinstance(wallet["type"], str)
            assert isinstance(wallet["currency"], str)
            assert isinstance(wallet["balance"], (int, float))
            assert isinstance(wallet["available"], (int, float))
            
            # Validate wallet type is one of the expected values
            assert wallet["type"] in ["exchange", "margin", "funding"]
            
            # Validate available is always >= 0 (even if None in source data)
            assert wallet["available"] >= 0


def test_wallet_available_balance_handling():
    """Test that available_balance is properly handled when it's None."""
    # Clear env to force paper mode (mock data)
    with patch.dict(os.environ, {}, clear=True):
        from importlib import reload
        import scripts.api_server as api_server_mod
        reload(api_server_mod)
        from scripts.api_server import _fetch_wallet_balances
        
        wallets = _fetch_wallet_balances()
    
        # In paper mode, all wallets should have available == balance
        for wallet in wallets:
            assert wallet["available"] == wallet["balance"]
