#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CENTRAL_MARK1="$ROOT_DIR/../github-copilot-config/agents/MARK1.md"
TARGET_MARK1="$ROOT_DIR/.github/agents/MARK1.agent.md"

if [[ ! -f "$CENTRAL_MARK1" ]]; then
  echo "ERROR: central MARK1 file not found: $CENTRAL_MARK1" >&2
  echo "Expected the github-copilot-config repo next to this repo." >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET_MARK1")"
cp "$CENTRAL_MARK1" "$TARGET_MARK1"

echo "Synced MARK1 → $TARGET_MARK1"
