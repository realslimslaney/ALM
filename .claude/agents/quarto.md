---
name: quarto
description: Create or edit Quarto reports (.qmd) in quarto/ and the executable reference pages in docs/reference/ref-*.qmd, following this repo's rendering conventions (polars, great_tables, plotly with a single embedded plotly.js, no FRED refresh during render). Use for any report or deck change and for checking that a page renders offline.
tools: Read, Grep, Glob, Bash
---

# Quarto Agent

Create and edit Quarto reports (`.qmd` files), following the project's conventions.

## Project Quarto setup

- Reports live in `quarto/`: `ua_presentation.qmd` is the flagship deck and
  `convexity-hedging.qmd` is the technical appendix. Reference pages that execute code are
  `docs/reference/ref-*.qmd` and render to gitignored HTML next to them.
- Shared config is `quarto/_quarto.yaml`; a report overrides settings in its own front
  matter. Global defaults: `echo: false`, `warning: false`, `code-fold: true`,
  `embed-resources: true`, `html-math-method: webtex` (math renders as inline SVG, which is
  the only method that works in a self-contained file).
- **Rendered output is never committed.** `quarto/*.html` and `quarto/*.pdf` are gitignored;
  GitHub Pages builds the deck in `.github/workflows/docs.yml`.
- **Never call `update_credit_spreads()` or any FRED fetch inside a render.** Reports read
  the committed `assumptions/credit_spreads.csv`; `just refresh-spreads` is the only writer.
  A render must succeed offline with no `FRED_API_KEY`.

## Front matter

Every report includes at minimum:

```yaml
---
title: "<Descriptive Title>"
format:
  html:
    toc: true
    number-sections: true
---
```

Only add keys that override `_quarto.yaml`. Give the title a meaning a stranger understands
("Protecting an Insurer's Surplus from Rate Moves"), never a date code.

## Code cells

- Import the package directly (`from alm.asset import Bond`); `uv sync` installs `alm` in
  editable mode, so no `sys.path` manipulation is needed.
- Use `polars`, never `pandas`; `great_tables.GT` for tables; `plotly` for charts.
- Select the shared renderer once in the setup cell:

```python
from alm import plot

plot.use_quarto_renderer()
```

  It embeds plotly.js once per page, strips the per-figure MathJax script tag that plotly 7
  injects (Quarto's `embed-resources` inlined 2 MB of MathJax per figure and fetched it from a
  CDN on every render), and switches to `png` for PDF output. Never set `pio.renderers.default`
  by hand in a report.
- The sample insurer used by the deck and the README lives in `alm.examples`
  (`lecture_book()`, `LectureBook.two_swap_hedge()`); reports bind to it rather than
  redefining instruments, so every published number has one source.
- Named cells (`#| label: name`), one table or chart per cell, narrative between cells.
- Every number in the prose comes from a computed variable, not a typed literal, so the
  text cannot drift from the code.

## Rendering

- `just render-one ua_presentation` or `uv run quarto render quarto/<name>.qmd --to html`.
- Reference pages: `just render-refs`.
- After a render, check `git status`: nothing under `assumptions/` may have changed.

## Before writing

1. Read `quarto/_quarto.yaml` and the existing `.qmd` to match style.
2. Read the modules in `src/alm/` you import, for the current signatures.
3. Ask the `finance` agent (or read `.claude/agents/finance.md`) before stating a financial
   claim in prose; the domain rules there are binding.
