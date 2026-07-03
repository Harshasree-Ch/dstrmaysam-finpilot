from __future__ import annotations

import sys
from pathlib import Path


def add_workspace_venv_site_packages(workspace_root: Path | None = None) -> None:
    """Allow local launches outside .venv to still see packages installed there."""
    root = workspace_root or Path(__file__).resolve().parents[3]
    candidates = [
        root / ".venv" / "Lib" / "site-packages",
        *sorted((root / ".venv" / "lib").glob("python*/site-packages")),
    ]
    for site_packages in candidates:
        if site_packages.exists() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
