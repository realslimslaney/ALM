# Code Review Agent

Review the provided code changes against the project's conventions and standards.

## Review Checklist

### Data Manipulation
- Verify **polars** is used instead of pandas for all data manipulation
- Flag any pandas imports or usage and suggest polars equivalents

### Code Style
- Functions must have **type hints** on all parameters and return types
- Functions should be **single-purpose** — flag functions doing too many things
- Look for **duplicated logic** that should be extracted into a reusable function in `src/alm/utils.py`
- Line length should not exceed **88 characters** (per ruff config)

### Project Structure
- Source code belongs in `src/alm/`
- Scripts belong in `scripts/` and should be runnable via `uv run python scripts/<name>.py`
- Tests belong in `tests/` and should be runnable via `uv run pytest`

### Linting
- Run `uv run ruff check` and `uv run ruff format --check` to catch style issues
- Summarize any ruff findings and suggest fixes

### Documentation
- If a new module was added to `src/alm/`, check that a matching reference page exists in `docs/reference/`
- Public functions should have clear, concise docstrings

## Output Format

Summarize findings in sections: **Issues**, **Suggestions**, and **Looks Good**. Be specific — reference file paths and line numbers.
