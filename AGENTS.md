# Agent Instructions (Codex and other coding agents)

Full project context lives in `.claude/CLAUDE.md`; follow it. Non-negotiables:

- **Package management**: uv only (`uv sync`, `uv add`, `uv remove`). Never pip.
- **Version bumps are mandatory with dependency changes**: whenever dependencies in
  `pyproject.toml` change (add, remove, or change a version constraint), increment the
  project `version` in `pyproject.toml` in the same commit (minor bump for new
  deps/features, patch bump for constraint-only changes, major for breaking API changes).
- **DataFrames**: Polars, not pandas.
- **Finance rules**: assets are valued at their own yield or purchase price, never at the
  risk-free rate; government bonds carry zero spread; DV01 (not Macaulay duration) is the
  risk measure for net cash flows and swaps; "immunization" means Redington, the two-swap
  solve is "DV01 + convexity matching"; short-duration liability blocks tilt toward
  government bonds. Every docstring states its rate basis and units.
- **Tests**: no network access; FRED is mocked; synthetic fixtures per `tests/` patterns;
  assert real values, not just types.
- **Never refresh FRED data during a Quarto render.** `just refresh-spreads` is the only
  writer of `assumptions/credit_spreads.csv`; reports read the committed snapshot.
- **Never commit rendered output** (`quarto/*.html`, `quarto/*.pdf`, `site/`) or secrets;
  use `.env` locally (see `.env.example`) and GitHub Actions secrets in CI.
- Run `just check` (ruff lint + format + pytest) before finishing.

## Committing and pull requests

- **Never commit without the user's explicit yes.** Once approved, delegate to the
  project-scoped `committer` agent ([`.codex/agents/committer.toml`](.codex/agents/committer.toml)
  for Codex, [`.claude/agents/committer.md`](.claude/agents/committer.md) for Claude), quoting
  the user's approval verbatim. Auto-accept or autonomous execution is not approval.
- Delegate PR creation and repair to the `pr_manager` agent
  ([`.codex/agents/pr-manager.toml`](.codex/agents/pr-manager.toml)). The committer never
  creates PRs; the PR manager never edits code, commits, pushes, or merges.
- Feature branch + PR always; never commit on `main`. Conventional Commits.

## Skills

- Codex skills in [`.agents/skills/`](.agents/skills/) are generated mirrors of
  `.claude/skills/`. Edit the Claude skill and run `just codex-skills-sync`; never edit a
  mirror by hand. `tests/test_codex_skill_mirrors.py` fails on drift.
- `$cross-review` asks Claude Code for a read-only second review of your change and records
  the exchange on the PR. `$post-plan` posts a plan to a GitHub issue.
