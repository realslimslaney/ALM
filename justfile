# ALM project task runner
# Install just: https://github.com/casey/just#installation

set windows-shell := ["powershell", "-NoLogo", "-NoProfile", "-Command"]
set dotenv-load

# List available recipes
default:
    @just --list

# Run pre-commit hooks and tests
check:
    uv run pre-commit run --all-files
    uv run pytest

# Run the test suite
test:
    uv run pytest

# Lint and format
lint:
    uv run ruff check .

format:
    uv run ruff format .

# --- Quarto rendering ---

# Render all QMD files to HTML
render:
    uv run quarto render quarto/ --to html

# Render all QMD files to PDF (requires TinyTeX: quarto install tinytex)
render-pdf:
    uv run quarto render quarto/ --to pdf

# Render a single QMD file to HTML: just render-one convexity-hedging
render-one name:
    uv run quarto render quarto/{{name}}.qmd --to html

# Render a single QMD file to PDF: just render-one-pdf convexity-hedging
render-one-pdf name:
    uv run quarto render quarto/{{name}}.qmd --to pdf

# --- Scripts ---

# Run a script: just run run_alm_demonstration
run name:
    uv run python scripts/{{name}}.py
