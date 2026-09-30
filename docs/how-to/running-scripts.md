# Running Scripts

Scripts in `scripts/` are standalone entry points that use the `alm` package. None of them
needs the network except `refresh_spreads.py`.

## Running a Script

1. Install the project once with `uv sync` (see [Getting Started](getting-started.md)).
2. Run a script by name with the `just` recipe, or directly with `uv`:

   ```bash
   just run run_alm_demonstration
   uv run python scripts/run_alm_demonstration.py
   ```

## The Scripts

| Script | What it does | Command |
|--------|--------------|---------|
| `run_alm_demonstration.py` | Offline block simulation: builds one `Block` per liability type (SPIA, WL, Term, FIA), generates backing assets per SAA, and prints cash-flow summaries. Reads the committed spread table; no network. | `just run run_alm_demonstration` |
| `refresh_spreads.py` | Rewrites `assumptions/credit_spreads.csv` from FRED. It is the only writer of that file and needs `FRED_API_KEY` in `.env`. Commit the CSV change on its own. | `just refresh-spreads` |
| `fixed_income_examples.py` | Prints every number in the [fixed-income reference](../reference/fixed-income.md): the 5-year bond duration and convexity example, the DV01 example, the two-swap hedge, and the IRR example. No network. | `just run fixed_income_examples` |
| `make_readme_chart.py` | Regenerates `images/surplus_vs_shock.png` and prints the README's headline table from the deck's sample insurer (`alm.examples`). No network. | `just run make_readme_chart` |

`cross_review.py` and `sync_codex_skills.py` are tooling for the AI assistants; use them
through `just cross-review` (see [Cross-Review a Change](how-to-cross-review-a-change.md)) and
`just codex-skills-sync`.

## Adding a New Script

1. Create a new `.py` file in `scripts/`.
2. Import what you need from `alm`; keep reusable logic in `src/alm/`, the script is only the
   entry point:

   ```python
   from alm.asset import Bond
   ```

3. Run it with `uv run python scripts/your_script.py` or `just run your_script`.
4. If it must never fetch FRED (the default), read `assumptions/credit_spreads.csv` through
   `alm.read` rather than calling the API.
