"""Utility functions for ALM."""

from pathlib import Path


def get_project_root(start: str | Path | None = None) -> Path:
    """
    Return the project root by searching upward for a marker file/dir.
    Defaults to the current file's directory if no start is provided.
    Raises FileNotFoundError if no root is found.
    """
    markers = {"pyproject.toml", ".git"}
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent

    for parent in (current, *current.parents):
        if any((parent / marker).exists() for marker in markers):
            return parent
    raise FileNotFoundError(f"Project root not found from start={current}")
