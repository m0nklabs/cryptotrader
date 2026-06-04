import os
import shutil
import glob

REPO_DIR = "/home/flip/agentic-stack-template"


def remove_path(path):
    full_path = os.path.join(REPO_DIR, path)
    if os.path.exists(full_path):
        print(f"Removing {path}...")
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)


def clean_file(path, keep_lines_containing=None):
    full_path = os.path.join(REPO_DIR, path)
    if not os.path.exists(full_path):
        return

    print(f"Cleaning {path}...")
    with open(full_path, "w") as f:
        if keep_lines_containing:
            f.write(keep_lines_containing)
        else:
            f.write("")


def main():
    # 1. Remove Trading Specific Directories
    dirs_to_remove = [
        "cex",
        "core/backtest",
        "core/execution",
        "core/fees",
        "core/market_cap",
        "core/market_data",  # We'll recreate a clean one
        "core/opportunities",
        "core/portfolio",
        "core/risk",
        "core/signals",
        "shared",
        "systemd",
        "tests/integration",
    ]
    for d in dirs_to_remove:
        remove_path(d)

    # 2. Remove Trading Specific Files in Core
    # (Most are gone with directories, but check for stragglers)

    # 3. Clean Scripts
    # Keep only infrastructure scripts
    scripts_to_keep = ["custom_agent.py", "approve_workflows.py", "healthcheck.py", "__init__.py", "README.md"]

    all_scripts = glob.glob(os.path.join(REPO_DIR, "scripts", "*"))
    for script in all_scripts:
        basename = os.path.basename(script)
        if basename not in scripts_to_keep:
            print(f"Removing script {basename}...")
            os.remove(script)

    # 4. Clean Tests
    # Remove all tests, create a simple sample test
    all_tests = glob.glob(os.path.join(REPO_DIR, "tests", "test_*.py"))
    for test in all_tests:
        os.remove(test)

    with open(os.path.join(REPO_DIR, "tests", "test_sample.py"), "w") as f:
        f.write(
            """def test_sample():
    assert True
"""
        )

    # 5. Clean API
    # Remove candle_stream.py
    remove_path("api/candle_stream.py")

    # Reset main.py to generic FastAPI
    with open(os.path.join(REPO_DIR, "api", "main.py"), "w") as f:
        f.write(
            """from fastapi import FastAPI

app = FastAPI(title="Agentic Stack API")

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/")
async def root():
    return {"message": "Welcome to the Agentic Stack Template"}
"""
        )

    # 6. Clean Frontend
    # Remove trading components
    remove_path("frontend/src/api")
    remove_path("frontend/src/components")
    os.makedirs(os.path.join(REPO_DIR, "frontend/src/components"), exist_ok=True)

    # Reset App.tsx
    with open(os.path.join(REPO_DIR, "frontend/src/App.tsx"), "w") as f:
        f.write(
            """import { useState } from 'react'

function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">🤖 Agentic Stack Template</h1>
        <p className="text-xl text-gray-400">Ready for your AI-native application.</p>
      </div>
    </div>
  )
}

export default App
"""
        )

    # 7. Clean Docs
    docs_to_remove = [
        "MARKET_CAP_RANKINGS.md",
        "REALTIME_CANDLES.md",
        "EXTENDED_INDICATORS_SUMMARY.md",
        "RISK_MANAGEMENT.md",
        "WEBSOCKET.md",
        "PORTS.md",  # Maybe keep but genericize? Remove for now.
        "ROADMAP_V2.md",
    ]
    for d in docs_to_remove:
        remove_path(f"docs/{d}")

    # 8. Clean DB Schema
    with open(os.path.join(REPO_DIR, "db", "schema.sql"), "w") as f:
        f.write(
            """-- Initial Schema
CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""
        )

    # 9. Clean Requirements
    # Remove trading libs (ccxt, pandas-ta, ta-lib, etc)
    # We'll just write a basic set
    with open(os.path.join(REPO_DIR, "requirements.txt"), "w") as f:
        f.write(
            """fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.25
asyncpg>=0.29.0
pydantic>=2.6.0
pydantic-settings>=2.1.0
python-dotenv>=1.0.0
openai>=1.10.0
"""
        )

    # 10. Clean Copilot Instructions
    with open(os.path.join(REPO_DIR, ".github", "copilot-instructions.md"), "w") as f:
        f.write(
            """# Repository custom instructions (Copilot)

These instructions apply to GitHub Copilot in the context of this repository.

## Primary goals

- Make the smallest correct change that satisfies the request.
- Keep the repo buildable/testable; don’t break CI.
- Prefer clarity and correctness over cleverness.

## Agent behavior

- **Execute, don't ask**: If you can run a command, create a file, or perform an action — do it immediately.
- **Minimize back-and-forth**: Complete tasks in one pass when possible.
- **Fix errors yourself**: If a command fails, debug and retry before asking the user for help.
- **NEVER do manual workarounds when automating**: Fix the automation instead.

## Engineering rules

- Follow existing patterns in the repo.
- Avoid adding dependencies unless they are clearly justified.
- Don’t introduce new features beyond what is requested.
- Keep changes focused.

## Technical Stack Reference

### Backend (Python)
- **Python**: 3.12+
- **Linting/Formatting**: ruff
- **Type checking**: pylance
- **Testing**: pytest, pytest-asyncio
- **Database**: PostgreSQL 16 via asyncpg / SQLAlchemy 2.0

### Frontend
- **Framework**: React 18+ with TypeScript
- **Build**: Vite
- **Styling**: Tailwind CSS

### Infrastructure
- **Container**: Docker, docker-compose
- **CI**: GitHub Actions
"""
        )

    print("Cleanup complete!")


if __name__ == "__main__":
    main()
