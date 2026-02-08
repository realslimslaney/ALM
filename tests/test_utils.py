"""Tests for alm.utils module."""

from pathlib import Path

import pytest

from alm.utils import get_project_root


class TestGetProjectRoot:
    """Tests for get_project_root."""

    def test_finds_root_from_src(self):
        """Starting inside src/ should find the project root."""
        root = get_project_root(Path(__file__).parent.parent / "src" / "alm")
        assert (root / "pyproject.toml").exists()

    def test_finds_root_from_tests(self):
        """Starting inside tests/ should find the project root."""
        root = get_project_root(Path(__file__))
        assert (root / "pyproject.toml").exists()

    def test_returns_path_object(self):
        root = get_project_root()
        assert isinstance(root, Path)

    def test_root_contains_expected_dirs(self):
        root = get_project_root()
        assert (root / "src").is_dir()
        assert (root / "tests").is_dir()

    def test_nonexistent_start_raises(self, tmp_path):
        """A path with no markers above it should raise FileNotFoundError."""
        isolated = tmp_path / "deep" / "nested" / "dir"
        isolated.mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="Project root not found"):
            get_project_root(isolated)
