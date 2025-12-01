"""Utility to expose the local cube_minimal sources without installing the package."""

from __future__ import annotations

import sys
from pathlib import Path


def add_repo_root_to_path() -> None:
    """Prepend repository root to sys.path so cube_minimal can be imported."""
    repo_root = Path(__file__).resolve().parents[2]
    repo_str = str(repo_root)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


# Run on import for convenience.
add_repo_root_to_path()

__all__ = ["add_repo_root_to_path"]
