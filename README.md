# ALM

Educational toolkit demonstrating Asset-Liability Management (ALM) concepts for actuarial science students. Built as a personal project for illustrative purposes only — not intended for professional use, financial advice, or production decision-making.

## Quick Start

**Prerequisites:** Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/realslimslaney/ALM.git
cd ALM
uv sync
uv run pytest
```

> New to development? See the [Environment Setup](docs/how-to/environment-setup.md) guide for step-by-step instructions.

## Documentation

- [Environment Setup](docs/how-to/environment-setup.md) — install VS Code, Git, Python, uv, and Quarto from scratch
- [Getting Started](docs/how-to/getting-started.md) — clone the repo, install dependencies, and verify
- [Running Scripts](docs/how-to/running-scripts.md) — execute scripts with `uv run`
- [Creating Quarto Reports](docs/how-to/creating-quarto-reports.md) — author and render `.qmd` reports
- [Project Structure](docs/reference/project-structure.md) — repository layout and conventions

## Development

```bash
uv run pre-commit install  # install git hooks (once)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pytest              # test
```

## License

[MIT](LICENSE)
