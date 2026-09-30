# ruff: noqa: E501  (ported verbatim from the sibling repos, which lint at 102/110 columns)
"""Codex skill mirrors: every Claude skill has an up-to-date .agents/skills copy, and nothing else does."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "sync_codex_skills", _REPO_ROOT / "scripts" / "sync_codex_skills.py"
)
sync_codex_skills = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sync_codex_skills)

SKILL = "---\nname: demo\ndescription: A demo skill.\n---\n\n# Demo\n\nRead `.claude/skills/demo/config.json`.\n"


def test_repo_mirrors_are_in_sync() -> None:
    """Editing a Claude skill without `just codex-skills-sync` fails here, and so the commit gate."""
    assert (
        sync_codex_skills.problems(sync_codex_skills.SOURCE_DIR, sync_codex_skills.MIRROR_DIR) == []
    )


def test_mirror_keeps_frontmatter_and_body_and_adds_the_codex_note() -> None:
    mirror = sync_codex_skills.render_mirror("demo", SKILL.replace("\n", "\r\n"))
    assert mirror.startswith("---\nname: demo\ndescription: A demo skill.\n---\n")
    assert mirror.endswith("# Demo\n\nRead `.claude/skills/demo/config.json`.\n")
    assert "> **Codex note.**" in mirror
    assert "Supporting files stay in `.claude/skills/demo/`" in mirror
    assert "`committer` is `committer`, `pr-manager` is `pr_manager`" in mirror
    assert "\r" not in mirror


def test_agents_line_names_ported_agents_when_they_exist() -> None:
    line = sync_codex_skills.agents_line({"pr-committer": "pr_committer"})
    assert (
        line
        == "> - Claude subagents are the Codex agents in `.codex/agents/`: `pr-committer` is `pr_committer`."
    )
    assert "no Codex port" in sync_codex_skills.agents_line({})


def test_sync_replaces_raw_copies_and_drops_orphans(tmp_path: Path) -> None:
    source_dir = tmp_path / "claude"
    mirror_dir = tmp_path / "agents"
    (source_dir / "demo").mkdir(parents=True)
    (source_dir / "demo" / "SKILL.md").write_text(SKILL, encoding="utf-8")
    (source_dir / "demo" / "config.json").write_text("{}", encoding="utf-8")
    (mirror_dir / "demo").mkdir(parents=True)
    (mirror_dir / "demo" / "SKILL.md").write_text("raw import copy", encoding="utf-8")
    (mirror_dir / "demo" / "config.json").write_text('{"stale": true}', encoding="utf-8")
    (mirror_dir / "retired").mkdir()
    (mirror_dir / "retired" / "SKILL.md").write_text("gone from .claude", encoding="utf-8")

    assert sync_codex_skills.problems(source_dir, mirror_dir) == [
        "stale: demo/SKILL.md",
        "extra: demo/config.json",
        "extra: retired/SKILL.md",
    ]
    assert sync_codex_skills.sync(source_dir, mirror_dir) == ["demo"]
    assert sync_codex_skills.problems(source_dir, mirror_dir) == []
    assert sorted(path.name for path in mirror_dir.rglob("*") if path.is_file()) == ["SKILL.md"]


def test_sync_normalizes_crlf_once_and_leaves_unchanged_mirrors_untouched(tmp_path: Path) -> None:
    source_dir = tmp_path / "claude"
    mirror_dir = tmp_path / "agents"
    source_path = source_dir / "demo" / "SKILL.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(SKILL, encoding="utf-8", newline="\r\n")
    mirror_path = mirror_dir / "demo" / "SKILL.md"
    mirror_path.parent.mkdir(parents=True)
    mirror_path.write_text(
        sync_codex_skills.render_mirror("demo", SKILL), encoding="utf-8", newline="\r\n"
    )

    sync_codex_skills.sync(source_dir, mirror_dir)
    assert b"\r" not in mirror_path.read_bytes()
    assert sync_codex_skills.problems(source_dir, mirror_dir) == []

    # An old timestamp makes an unnecessary rewrite detectable even on coarse filesystems.
    os.utime(mirror_path, ns=(1_000_000_000, 1_000_000_000))
    previous_mtime = mirror_path.stat().st_mtime_ns
    sync_codex_skills.sync(source_dir, mirror_dir)
    assert mirror_path.stat().st_mtime_ns == previous_mtime


def test_hand_written_codex_versions_are_left_alone(tmp_path: Path) -> None:
    source_dir = tmp_path / "claude"
    mirror_dir = tmp_path / "agents"
    for name in ("demo", "other"):
        (source_dir / name).mkdir(parents=True)
        (source_dir / name / "SKILL.md").write_text(SKILL.replace("demo", name), encoding="utf-8")
    custom = (
        f"---\nname: demo\ndescription: Codex-specific.\n---\n\n{sync_codex_skills.CUSTOM_MARKER}\n"
    )
    (mirror_dir / "demo").mkdir(parents=True)
    (mirror_dir / "demo" / "SKILL.md").write_text(custom, encoding="utf-8")
    (mirror_dir / "demo" / "helper.py").write_text("print('codex')", encoding="utf-8")
    (mirror_dir / "codex-only").mkdir()
    (mirror_dir / "codex-only" / "SKILL.md").write_text(
        custom.replace("demo", "codex-only"), encoding="utf-8"
    )

    assert sync_codex_skills.sync(source_dir, mirror_dir) == ["other"]
    assert (mirror_dir / "demo" / "SKILL.md").read_text(encoding="utf-8") == custom
    assert (mirror_dir / "demo" / "helper.py").exists()
    assert (mirror_dir / "codex-only" / "SKILL.md").exists()
    assert sync_codex_skills.problems(source_dir, mirror_dir) == []


def test_agents_without_a_codex_port_are_reported_not_copied(tmp_path: Path) -> None:
    claude_agents = tmp_path / "claude-agents"
    codex_agents = tmp_path / "codex-agents"
    claude_agents.mkdir()
    codex_agents.mkdir()
    for name in ("committer", "analyst"):
        (claude_agents / f"{name}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (codex_agents / "committer.toml").write_text('name = "committer"\n', encoding="utf-8")

    assert sync_codex_skills.missing_agent_ports(claude_agents, codex_agents) == ["analyst"]
    assert sorted(path.name for path in codex_agents.iterdir()) == ["committer.toml"]
