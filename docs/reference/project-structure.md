# Project Structure

## `src/alm/`

The core Python package. All reusable functions and modules live here. Import with:

```python
import alm
from alm import module_name
```

Add a new reference page under `docs/reference/` for each major module or process added to this package.

## `scripts/`

Standalone Python scripts that use the `alm` package to perform specific tasks (e.g. running a model, generating output). These are not importable — they are entry points.

## `quarto/`

Quarto `.qmd` files for generating reports, visualizations, and graphs. Each file typically imports from `alm` and produces rendered HTML or PDF output.

## `tests/`

Pytest test suite. Run with:

```bash
uv run pytest
```

## Linting and Formatting

Configured via `[tool.ruff]` in `pyproject.toml`. Uses [ruff](https://docs.astral.sh/ruff/) with the following rule sets: pycodestyle, pyflakes, isort, pyupgrade, bugbear, and simplify.

```bash
uv run ruff check .       # lint
uv run ruff format .      # format
```

## `docs/`

Project documentation following the [Diataxis](https://diataxis.fr/) framework:

| Section    | Purpose                                          |
|------------|--------------------------------------------------|
| how-to/    | Step-by-step guides for accomplishing tasks      |
| reference/ | Technical descriptions of modules and processes  |
