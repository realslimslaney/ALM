# Getting Started

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

> **New to development?** See the [Environment Setup](environment-setup.md) guide for
> step-by-step instructions to install all prerequisites.

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/realslimslaney/ALM.git
   cd ALM
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Install pre-commit hooks:

   ```bash
   uv run pre-commit install
   ```

4. Verify the installation:

   ```bash
   uv run pytest
   ```

## Linting and Formatting

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
uv run ruff check .       # lint
uv run ruff format .      # format
```

## Project Layout

```
ALM/
├── src/alm/        # Importable Python package
├── scripts/        # Standalone runnable scripts
├── quarto/         # Quarto (.qmd) reports and graphs
├── tests/          # Test suite
└── docs/           # Documentation
```
