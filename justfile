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

# --- Documentation ---

# Render Quarto reference pages to HTML
render-refs:
    uv run quarto render docs/reference/ref-spia.qmd --to html
    uv run quarto render docs/reference/ref-whole-life.qmd --to html
    uv run quarto render docs/reference/ref-term-life.qmd --to html
    uv run quarto render docs/reference/ref-fia.qmd --to html

# Render Quarto refs + serve docs locally with live reload
docs-serve: render-refs
    uv run mkdocs serve

# Render Quarto refs + build docs site to site/
docs-build: render-refs
    uv run mkdocs build --strict

# --- Quarto rendering ---

# Render all QMD files to HTML (quarto/ + reference pages)
render: render-refs
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
