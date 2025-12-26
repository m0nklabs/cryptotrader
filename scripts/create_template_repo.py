import os
import shutil
import subprocess
import sys

# Configuration
TEMPLATE_NAME = "agentic-stack-template"
SOURCE_DIR = os.getcwd()
DEST_DIR = os.path.abspath(os.path.join(SOURCE_DIR, "..", TEMPLATE_NAME))


def run_command(command, cwd=None):
    try:
        subprocess.run(command, shell=True, check=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command '{command}': {e.stderr.decode()}", file=sys.stderr)
        return False


def main():
    print(f"🚀 Creating template repository '{TEMPLATE_NAME}' from current workspace...")

    # 1. Prepare Destination
    if os.path.exists(DEST_DIR):
        print(f"   ⚠️  Removing existing directory {DEST_DIR}...")
        shutil.rmtree(DEST_DIR)
    os.makedirs(DEST_DIR)

    # 2. Export clean copy using git archive (ignores .git, .gitignore files, etc)
    print("   📦 Exporting files...")
    if not run_command(f"git archive HEAD | tar -x -C {DEST_DIR}"):
        print("Failed to export files.")
        return

    # 3. Prune specific business logic (Keep structure, remove implementation)
    print("   🧹 Pruning specific business logic...")

    # List of directories to empty (but keep the folder)
    dirs_to_empty = [
        "core/strategies",
        "core/indicators",
        "core/analysis",
        "api/exchanges",
        "frontend/src/components/trading",
        "frontend/src/components/dashboard",
        "frontend/src/hooks/trading",
    ]

    for rel_path in dirs_to_empty:
        full_path = os.path.join(DEST_DIR, rel_path)
        if os.path.exists(full_path):
            shutil.rmtree(full_path)
            os.makedirs(full_path)
            with open(os.path.join(full_path, ".gitkeep"), "w") as f:
                f.write("")

    # 4. Generalize Configuration
    print("   ⚙️  Generalizing configuration...")

    # Replace 'cryptotrader' with 'agentic-project' in key files
    files_to_scrub = ["pyproject.toml", "docker-compose.yml", ".devcontainer/devcontainer.json", "package.json"]

    for rel_path in files_to_scrub:
        file_path = os.path.join(DEST_DIR, rel_path)
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                content = f.read()

            new_content = content.replace("cryptotrader", "agentic-project")

            with open(file_path, "w") as f:
                f.write(new_content)

    # 5. Create new README
    readme_content = """# Agentic Stack Template 🤖

This is a production-ready template for building AI-native applications, extracted from the [Cryptotrader](https://github.com/m0nklabs/cryptotrader) project.

## Features

- **🤖 Agentic Workflows**: Pre-configured GitHub Actions for Copilot Agents, Auto-Review, and Custom LLM Agents.
- **🐳 DevContainer**: Fully isolated development environment with Python 3.12, Node 20, and PostgreSQL 16.
- **🐍 Backend**: FastAPI/Python structure with SQLAlchemy and Pydantic.
- **⚛️ Frontend**: React/Vite setup with Tailwind CSS.
- **🔄 CI/CD**: Robust pipelines for testing, linting, and auto-assignment.

## Getting Started

1. Click **"Use this template"** to create a new repository.
2. Open in GitHub Codespaces or VS Code DevContainers.
3. Run `pip install -r requirements.txt` and `npm install`.

## Agent Configuration

Check `.github/workflows/` to see the available agentic workflows.
"""
    with open(os.path.join(DEST_DIR, "README.md"), "w") as f:
        f.write(readme_content)

    # 6. Initialize new Git Repo
    print("   ✨ Initializing new git repository...")
    run_command("git init", cwd=DEST_DIR)
    run_command("git add .", cwd=DEST_DIR)
    run_command("git commit -m 'feat: initial commit from Agentic Stack Template'", cwd=DEST_DIR)

    print(f"\n✅ Template created successfully at: {DEST_DIR}")
    print("\nTo publish this to GitHub, run:")
    print(f"  cd {DEST_DIR}")
    print(f"  gh repo create m0nklabs/{TEMPLATE_NAME} --public --source=. --remote=origin --push --template")


if __name__ == "__main__":
    main()
