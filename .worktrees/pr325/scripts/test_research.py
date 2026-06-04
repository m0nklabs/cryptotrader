#!/usr/bin/env python3
"""Quick test script for research endpoint."""

import asyncio
import httpx


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test without LLM
        print("Testing /research/BTCUSD...")
        try:
            resp = await client.get("http://localhost:8000/research/BTCUSD")
            if resp.status_code == 200:
                data = resp.json()
                print("✅ Success!")
                print(f"   Recommendation: {data['recommendation']}")
                print(f"   Confidence: {data['confidence']}%")
                print(f"   Price: {data['current_price']}")
                print(f"   Reasoning: {data['reasoning'][:3]}...")
            else:
                print(f"❌ Error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"❌ Request failed: {e}")

        # Test LLM status
        print("\nTesting /research/llm/status...")
        try:
            resp = await client.get("http://localhost:8000/research/llm/status")
            print(f"   LLM Status: {resp.json()}")
        except Exception as e:
            print(f"❌ LLM status failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
