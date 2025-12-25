#!/usr/bin/env bash
# Push workflow files using GitHub App token
# Usage: ./scripts/push-workflows.sh <APP_ID> <INSTALLATION_ID> <PRIVATE_KEY_PATH>

set -e

APP_ID="${1:-}"
INSTALLATION_ID="${2:-}"
PRIVATE_KEY="${3:-/home/flip/.secrets/flip-devops-bot.pem}"

if [ -z "$APP_ID" ] || [ -z "$INSTALLATION_ID" ]; then
    echo "Usage: $0 <APP_ID> <INSTALLATION_ID> [PRIVATE_KEY_PATH]"
    echo ""
    echo "Get these values from:"
    echo "  APP_ID: Your GitHub App settings page"
    echo "  INSTALLATION_ID: URL after installing the app (https://github.com/settings/installations/<ID>)"
    echo ""
    echo "See docs/GITHUB_APP_SETUP.md for full instructions"
    exit 1
fi

if [ ! -f "$PRIVATE_KEY" ]; then
    echo "Error: Private key not found at $PRIVATE_KEY"
    exit 1
fi

# Check if gh-token extension is installed
if ! gh extension list | grep -q "gh-token"; then
    echo "Installing gh-token extension..."
    gh extension install Link-/gh-token
fi

# Generate installation token
echo "Generating GitHub App installation token..."
TOKEN=$(gh token generate --app-id "$APP_ID" --installation-id "$INSTALLATION_ID" --key "$PRIVATE_KEY" 2>/dev/null | grep "^Token:" | cut -d' ' -f2)

if [ -z "$TOKEN" ]; then
    # Try alternative format
    TOKEN=$(gh token generate --app-id "$APP_ID" --installation-id "$INSTALLATION_ID" --key "$PRIVATE_KEY" 2>/dev/null)
fi

if [ -z "$TOKEN" ]; then
    echo "Error: Could not generate token"
    exit 1
fi

echo "Token generated successfully"

# Configure git to use the token
REPO_URL="https://x-access-token:${TOKEN}@github.com/m0nk111/cryptotrader.git"

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Committing pending changes..."
    git add -A
    git commit -m "feat(ci): add pre-commit job and Copilot rebase helper

- Add pre-commit job to CI workflow
- Add copilot-rebase.yml for automatic PR rebasing
- Update copilot-auto-assign.yml to use GitHub App token
- Add GITHUB_APP_SETUP.md documentation"
fi

# Push using the app token
echo "Pushing to GitHub..."
git push "$REPO_URL" master

echo ""
echo "✅ Successfully pushed workflow files!"
echo ""
echo "Next steps:"
echo "1. Add APP_ID and APP_PRIVATE_KEY secrets to GitHub:"
echo "   https://github.com/m0nk111/cryptotrader/settings/secrets/actions"
echo ""
echo "2. Configure local git to use the app token permanently:"
echo "   git remote set-url origin $REPO_URL"
