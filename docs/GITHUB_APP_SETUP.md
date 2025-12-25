# GitHub App Setup for m0nklabs

Deze GitHub App geeft volledige permissions voor:
- Workflow file updates
- Force push (rebase)
- Copilot agent operations

Werkt voor **alle repositories** onder de m0nklabs org.

## Huidige configuratie

| Setting | Value |
|---------|-------|
| **App Name** | `m0nk1111-devops-bot` |
| **App ID** | `2537261` |
| **Owner** | `m0nk1111` |
| **Installation ID (m0nklabs)** | `101203273` |
| **Installation ID (m0nk1111)** | `101198890` |
| **Private Key** | `/home/flip/.secrets/m0nk1111-devops-bot.2025-12-25.private-key.pem` |

## Permissions

| Permission | Access |
|------------|--------|
| Actions | Read and write |
| Contents | Read and write |
| Issues | Read and write |
| Metadata | Read-only |
| Pull requests | Read and write |
| Workflows | Read and write |

## Repository Secrets

De volgende secrets zijn geconfigureerd op `m0nklabs/cryptotrader`:

| Secret | Description |
|--------|-------------|
| `APP_ID` | `2537261` |
| `APP_PRIVATE_KEY` | Content van de .pem file |

## Lokale CLI gebruik

```bash
# Genereer een token voor m0nklabs repos
gh token generate \
  --app-id 2537261 \
  --installation-id 101203273 \
  --key /home/flip/.secrets/m0nk1111-devops-bot.2025-12-25.private-key.pem
```

## Workflows

De CI workflows gebruiken `tibdex/github-app-token` action:

```yaml
- name: Generate token
  id: generate-token
  uses: tibdex/github-app-token@v2
  with:
    app_id: ${{ secrets.APP_ID }}
    private_key: ${{ secrets.APP_PRIVATE_KEY }}
```
