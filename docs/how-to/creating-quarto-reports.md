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
just render-one-pdf your_report    # single report to PDF
just render                        # all reports to HTML
just render-pdf                    # all reports to PDF
```

> **PDF output** requires a LaTeX distribution. Install TinyTeX via Quarto:
> `quarto install tinytex`
