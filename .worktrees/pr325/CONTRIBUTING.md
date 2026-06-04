# Contributing to cryptotrader

## Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 16 (or use Docker)
- Git

### Quick Start

```bash
# Clone the repo
git clone https://github.com/m0nk111/cryptotrader.git
cd cryptotrader

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Run tests
pytest

# Start backend (example)
python -m api.main

# Frontend setup
cd frontend
npm install
npm run dev  # Runs on port 5176
```

### Using DevContainer (Recommended)

Open the repo in VS Code and select "Reopen in Container" when prompted. This gives you:
- Python 3.12 + Node 20
- PostgreSQL 16
- All dependencies pre-installed
- Pre-commit hooks ready

## Code Style

- **Python**: Formatted and linted by [ruff](https://github.com/astral-sh/ruff)
- **Frontend**: Prettier + ESLint
- **Commits**: Conventional commits preferred (`feat:`, `fix:`, `chore:`, etc.)

Pre-commit hooks run automatically on each commit.

## Pull Request Process

1. **Check existing issues** — look for related issues/Epics before starting
2. **Create a branch** — `feature/issue-number-short-description` or `fix/issue-number-short-description`
3. **Make changes** — follow existing patterns
4. **Add tests** — minimum 80% coverage for new code
5. **Run checks**:
   ```bash
   ruff check .
   pytest
   ```
6. **Open PR** — use the PR template, link to issue
7. **Wait for review** — CODEOWNERS will be auto-assigned

## Issue Workflow

We use GitHub Issues with Epics:
- **Epics** (`🎯 EPIC:`) group related work
- **Sub-issues** are linked to Epics
- Use issue templates for bugs, features, and epics

## Trading Code Rules

⚠️ **Safety is paramount** for trading code:

1. **Paper trading by default** — all execution code must have `dry_run=True` or `paper_mode=True` as default
2. **Never commit secrets** — use `.env` and environment variables
3. **Log all orders** — include symbol, side, size, price, timestamp
4. **Enforce limits** — position size limits per symbol and portfolio-wide
5. **Handle errors** — network errors, API errors, partial fills

## Questions?

Open a Discussion or Issue if you're unsure about anything.
