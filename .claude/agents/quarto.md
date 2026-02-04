# Quarto Agent

Create and edit Quarto reports (`.qmd` files) in the `quarto/` directory, following the project's established conventions.

## Project Quarto Setup

- All `.qmd` files live in `quarto/`
- Shared config is in `quarto/_quarto.yaml` — individual reports can override settings in their YAML front matter
- The Python executable is the local `.venv`: `execute.python: ".venv/Scripts/python.exe"`
- Global defaults: `echo: false`, `warning: false`, `code-fold: true`, `embed-resources: true`

## YAML Front Matter

Every `.qmd` report should include at minimum:

```yaml
---
title: "<Report Title>"
format:
  html:
    toc: true
    number-sections: true
    self-contained: true
  pdf:
    toc: true
    number-sections: true
    geometry:
      - left=0.5in
      - right=0.5in
      - top=0.5in
      - bottom=0.5in
    papersize: letter
    fontsize: 11pt
---
```

Only add format keys that **override** `_quarto.yaml` — do not duplicate defaults unnecessarily.

## Code Cells

### Imports cell
The first code cell should handle imports and environment setup. Follow this pattern:

```{python imports}
from pathlib import Path
import sys
import polars as pl

sys.path.insert(0, str((Path.cwd().parent) / "src"))
from alm import ...
```

- Use `polars`, never `pandas`
- Import from `src/alm/` using the `sys.path` pattern above
- Handle PDF vs HTML renderer switching for plotly:

```python
import os, plotly.io as pio
pdf_bool = os.environ.get("QUARTO_PROJECT_OUTPUT_FORMAT") == "pdf"
pio.renderers.default = "png" if pdf_bool else "notebook_connected+vscode"
```

### Content cells
- Use **named code cells** where appropriate: `` ```{python cell-name} ``
- Keep cells focused — one visualization or one table per cell
- Use `great_tables.GT` for styled tables and `plotly` for charts
- Add markdown narrative between cells to explain findings

## Rendering

- Render HTML: `uv run quarto render quarto/<name>.qmd --to html`
- Render PDF: `uv run quarto render quarto/<name>.qmd --to pdf`

## Before Writing

1. Read `quarto/_quarto.yaml` to confirm current shared config
2. Read existing `.qmd` files in `quarto/` to match the established style
3. Read relevant source modules in `src/alm/` to use the correct imports and function signatures
