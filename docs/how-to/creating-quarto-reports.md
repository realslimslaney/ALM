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
uv run quarto render quarto/your_report.qmd
```
