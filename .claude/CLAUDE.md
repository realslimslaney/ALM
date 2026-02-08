# Project Guidelines

## Terminology

- **ALM** stands for **Asset-Liability Management**

## General

- This is an educational ALM (Asset-Liability Management) toolkit for actuarial science students
- Source code lives in `src/alm/`, scripts in `scripts/`, quarto reports in `quarto/`

## Code Style

- Use polars over pandas whenever possible for data manipulation
- Create re-usable functions for abstract, repeatable tasks — avoid duplicating logic
- Keep functions focused and single-purpose
- Use type hints on function signatures

## Documentation

- Documentation lives in `docs/` and follows the [Diataxis](https://diataxis.fr/) framework
- **How-to guides** (`docs/how-to/`): step-by-step instructions for common tasks
- **Reference** (`docs/reference/`): technical descriptions of modules and processes
- When a major new process or module is added to `src/alm/`, add a corresponding reference page in `docs/reference/`
- Keep docs concise and up to date with code changes

## Dependencies

- Manage dependencies with `uv`
- Run scripts via `uv run python scripts/<name>.py`
- Run tests via `uv run pytest`
- Run all checks (pre-commit + tests) via `just check`
