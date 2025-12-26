#!/usr/bin/env python3
"""Install cryptotrader systemd services for the current user.

What it does:
- Links all unit files from systemd/ to ~/.config/systemd/user/
- Reloads the systemd user daemon.
- Enables and starts the core services (API and Frontend).
- Suggests enabling linger for persistent execution.
"""

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SYSTEMD_SRC = _REPO_ROOT / "systemd"
_SYSTEMD_DST = Path.home() / ".config" / "systemd" / "user"

CORE_SERVICES = [
    "cryptotrader-dashboard-api.service",
    "cryptotrader-frontend.service",
]


def _run(cmd: list[str]) -> None:
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> int:
    if not _SYSTEMD_SRC.exists():
        print(f"Error: {_SYSTEMD_SRC} does not exist.")
        return 1

    print(f"Installing services from {_SYSTEMD_SRC} to {_SYSTEMD_DST}...")
    _SYSTEMD_DST.mkdir(parents=True, exist_ok=True)

    # Link all .service and .timer files
    units_linked = 0
    for unit_file in _SYSTEMD_SRC.glob("*.*"):
        if unit_file.suffix not in (".service", ".timer"):
            continue

        dest_link = _SYSTEMD_DST / unit_file.name
        if dest_link.exists() or dest_link.is_symlink():
            if dest_link.resolve() == unit_file:
                print(f"  [OK] {unit_file.name} already linked.")
                continue
            else:
                print(f"  [WARN] {unit_file.name} exists but points elsewhere. Overwriting...")
                dest_link.unlink()

        dest_link.symlink_to(unit_file)
        print(f"  [NEW] Linked {unit_file.name}")
        units_linked += 1

    if units_linked > 0:
        _run(["systemctl", "--user", "daemon-reload"])

    # Enable and start core services
    for service in CORE_SERVICES:
        _run(["systemctl", "--user", "enable", "--now", service])

    print("\nServices installed and started!")
    print("To ensure services run after logout, run:")
    print(f"  loginctl enable-linger {os.environ.get('USER', 'current_user')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
