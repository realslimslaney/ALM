# Getting Started

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [just](https://github.com/casey/just) (task runner)

### Installing just

| Platform | Command |
|----------|---------|
| **Windows (Chocolatey)** | `choco install just` |
| **Windows (WinGet)** | `winget install Casey.Just` |
| **Windows (Scoop)** | `scoop install just` |
| **macOS (Homebrew)** | `brew install just` |
| **Linux (apt — Ubuntu/Debian)** | `sudo apt install just` |
| **Linux (Homebrew)** | `brew install just` |
| **Any (cargo)** | `cargo install just` |
| **Any (pipx)** | `pipx install rust-just` |

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

4. Set up your API keys:

   Copy the example environment file and add your keys:

   ```bash
   cp .env.example .env
   ```

   Open `.env` and replace `your_key_here` with your
   [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) (free).

5. Verify the installation:

   ```bash
   uv run pytest
   ```

## Common Tasks

This project uses [just](https://github.com/casey/just) as a task runner. Run `just` with no arguments to see all available recipes.

```bash
just              # list all recipes
just test         # run tests
just lint         # lint with ruff
just format       # format with ruff
just render       # render all QMD files to HTML
just render-pdf   # render all QMD files to PDF
just render-one convexity-hedging      # render a single report to HTML
just render-one-pdf convexity-hedging  # render a single report to PDF
just run run_alm_demonstration         # run a script
```

> **PDF output** requires a LaTeX distribution. Install TinyTeX via Quarto:
> `quarto install tinytex`

## Project Layout

```
ALM/
├── src/alm/        # Importable Python package
├── scripts/        # Standalone runnable scripts
├── quarto/         # Quarto (.qmd) reports and graphs
├── tests/          # Test suite
└── docs/           # Documentation
```
