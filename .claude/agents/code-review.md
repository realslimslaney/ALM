---
name: code-review
description: Review a diff or branch against this repo's conventions (polars, type hints, single-purpose functions, ruff at 100 columns, docs kept in sync) and against the finance domain rules. Use before opening a PR or when asked for a review of local changes.
tools: Read, Grep, Glob, Bash
---

# Code Review Agent

Review the provided code changes against the project's conventions and standards.

## Review checklist

### Data manipulation
- Verify **polars** is used instead of pandas for all data manipulation.
- Flag any pandas imports or usage and suggest polars equivalents.

### Code style
- Functions have **type hints** on all parameters and return types.
- Functions are **single-purpose**; flag functions doing too many things.
- Look for **duplicated logic** that should be extracted into a reusable function.
- Line length does not exceed **100 characters** (`[tool.ruff]` in `pyproject.toml`).
- No opaque variable names.

### Domain correctness (anything under `src/alm/`, `quarto/`, `docs/reference/`)
- Apply the rules in `.claude/agents/finance.md`: assets valued at their own yield, zero
  spread on government bonds, DV01 for net cash flows and swaps, Redington stated correctly,
  promised vs expected yield, rate basis and units in docstrings.
- A number that appears in prose or a table must be produced by code in the same file.

### Project structure
- Source code belongs in `src/alm/`; scripts in `scripts/`; tests in `tests/`.
- Rendered Quarto output (`quarto/*.html`, `*.pdf`) is never in the diff.
- `assumptions/credit_spreads.csv` changes only in a `just refresh-spreads` commit.
- A dependency change in `pyproject.toml` comes with a version bump and an `uv.lock` update.

### Linting and tests
- Run `uv run ruff check .` and `uv run ruff format --check .`; summarize findings.
- Run `uv run pytest -q`; new behaviour has tests that assert real values, not just types.

### Documentation
- A new or removed public function is reflected in `docs/reference/`.
- Public functions have clear, concise docstrings.

## Output format

Summarize findings in sections: **Issues**, **Suggestions**, and **Looks Good**. Be specific;
reference file paths and line numbers.
