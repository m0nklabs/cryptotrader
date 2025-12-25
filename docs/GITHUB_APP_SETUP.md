# GitHub App Setup for m0nk111 repositories

Deze GitHub App geeft volledige permissions voor:
- Workflow file updates
- Force push (rebase)
- Copilot agent operations

Werkt voor **alle repositories** onder je account.

## Stap 1: Maak de GitHub App

1. Ga naar: https://github.com/settings/apps/new
2. Vul in:
   - **GitHub App name**: `m0nk111-bot` (of `flip-bot`)
   - **Homepage URL**: `https://github.com/m0nk111`
   - **Webhook**: Uncheck "Active" (niet nodig)

3. **Repository permissions**:
   | Permission | Access |
   |------------|--------|
   | Actions | Read and write |
   | Contents | Read and write |
   | Issues | Read and write |
   | Metadata | Read-only |
   | Pull requests | Read and write |
   | Workflows | Read and write |

4. **Where can this GitHub App be installed?**: Only on this account

5. Klik **Create GitHub App**

## Stap 2: Genereer Private Key

1. Na het maken, scroll naar "Private keys"
2. Klik **Generate a private key**
3. Download het `.pem` bestand
3. Sla op als `/home/flip/.secrets/flip-devops-bot.pem`

## Stap 3: Installeer de App op je account

1. Ga naar je App settings → Install App
2. Selecteer je account
3. Kies **"All repositories"** voor alle repos, of selecteer specifieke repos
4. Klik **Install**

## Stap 4: Noteer de IDs

Na installatie, noteer:
- **App ID**: Te vinden op de App settings pagina (bijv. `123456`)
- **Installation ID**: In de URL na installatie (bijv. `https://github.com/settings/installations/12345678` → `12345678`)

## Stap 5: Voeg secrets toe aan GitHub

Ga naar: https://github.com/m0nk111/cryptotrader/settings/secrets/actions

Voeg toe:
1. **`APP_ID`**: De App ID
2. **`APP_PRIVATE_KEY`**: Inhoud van het `.pem` bestand

## Stap 6: Lokale CLI configureren

```bash
# Installeer gh-token extensie (genereert installation tokens)
gh extension install Link-/gh-token

# Genereer een token voor lokaal gebruik
gh token generate \
  --app-id <APP_ID> \
  --installation-id <INSTALLATION_ID> \
  --key /home/flip/.secrets/flip-devops-bot.pem

# Of maak een alias voor gemak
echo 'alias ghtoken="gh token generate --app-id <APP_ID> --installation-id <INSTALLATION_ID> --key /home/flip/.secrets/flip-devops-bot.pem"' >> ~/.bashrc
```

## Stap 7: Git remote configureren

```bash
# Optie A: Gebruik de token in de URL (niet recommended)
git remote set-url origin https://x-access-token:$(ghtoken)@github.com/m0nk111/cryptotrader.git

# Optie B: Gebruik git credential helper (recommended)
git config --global credential.helper store
echo "https://x-access-token:$(ghtoken)@github.com" >> ~/.git-credentials
```

## Workflows die de App gebruiken

De CI workflows gebruiken `tibdex/github-app-token` action om een installation token te genereren:

```yaml
- name: Generate token
  id: generate-token
  uses: tibdex/github-app-token@v2
  with:
    app_id: ${{ secrets.APP_ID }}
    private_key: ${{ secrets.APP_PRIVATE_KEY }}

- name: Checkout with token
  uses: actions/checkout@v4
  with:
    token: ${{ steps.generate-token.outputs.token }}
```

## Validatie

Test de setup:

```bash
# Check token scopes
gh auth status

# Test workflow push
git checkout -b test-workflow-push
echo "# test" >> .github/workflows/ci.yml
git add . && git commit -m "test"
git push origin test-workflow-push
git checkout master
git branch -D test-workflow-push
git push origin --delete test-workflow-push
```

## Troubleshooting

### "refusing to allow an OAuth App to create or update workflow"
- De token mist `workflow` scope
- Gebruik de GitHub App token in plaats van OAuth token

### Copilot kan niet rebasen
- Copilot heeft een token nodig met `contents: write` en force-push permissions
- De GitHub App lost dit op via de installation token

### Token expired
- GitHub App installation tokens zijn 1 uur geldig
- Regenereer met `gh token generate` of gebruik de action in CI
