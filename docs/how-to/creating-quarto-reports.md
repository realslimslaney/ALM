# Creating Quarto Reports

Quarto (`.qmd`) files in `quarto/` are used to generate reports and graphs.

## Prerequisites

- [Quarto CLI](https://quarto.org/docs/get-started/)

## Creating a New Report

1. Create a `.qmd` file in `quarto/`:

   ```yaml
   ---
   title: "Your Report Title"
   format: html
   ---
   ```

2. Add Python code cells that import from `alm`:

   ````markdown
   ```{python}
   from alm import some_function
   ```
   ````

## Rendering

```bash
just render-one your_report        # single report to HTML
just render                        # all reports to HTML
just render-refs                   # executable reference pages in docs/reference/
```

Rendered output (`quarto/*.html`) is gitignored; GitHub Pages renders and publishes the
reports from `.github/workflows/docs.yml`. A report must render offline: never fetch FRED
inside a report. Reports read the committed `assumptions/credit_spreads.csv`, which only
`just refresh-spreads` updates.
