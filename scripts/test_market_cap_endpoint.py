#!/usr/bin/env python3
"""Test script to verify market cap endpoint works."""

import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from api.main import app


def test_market_cap_endpoint():
    """Test the /market-cap endpoint."""
    client = TestClient(app)

    print("Testing /market-cap endpoint...")
    response = client.get("/market-cap")

    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.json()
    print(f"Response keys: {list(data.keys())}")

    assert "rankings" in data, "Missing 'rankings' key"
    assert "cached" in data, "Missing 'cached' key"
    assert "source" in data, "Missing 'source' key"
    assert "last_updated" in data, "Missing 'last_updated' key"

    rankings = data["rankings"]
    print(f"Number of coins in rankings: {len(rankings)}")
    print(f"Source: {data['source']}")
    print(f"Cached: {data['cached']}")

    # Show top 10
    top_10 = sorted(rankings.items(), key=lambda x: x[1])[:10]
    print("\nTop 10 coins by market cap:")
    for symbol, rank in top_10:
        print(f"  {rank:3d}. {symbol}")

    print("\n✅ Market cap endpoint test passed!")


if __name__ == "__main__":
    test_market_cap_endpoint()
