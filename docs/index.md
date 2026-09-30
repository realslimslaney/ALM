# ALM Documentation

Educational toolkit demonstrating Asset-Liability Management (ALM) concepts for actuarial science students.

## Start here

- [ALM deck](https://realslimslaney.github.io/ALM/quarto/ua_presentation.html) — the flagship presentation: a life insurer's liabilities, the assets backing them, and the DV01 and convexity hedge that keeps surplus stable when rates move.
- [Convexity hedging appendix](https://realslimslaney.github.io/ALM/quarto/convexity-hedging.html) — the two-swap DV01 and dollar-convexity solve behind the deck, worked through step by step.

## How-to Guides

Step-by-step instructions to help you get started and accomplish common tasks.

- [Environment Setup](how-to/environment-setup.md) — install VS Code, Git, Python, uv, and Quarto from scratch
- [Getting Started](how-to/getting-started.md) — clone, `uv sync`, pre-commit, API key, run the tests
- [Running Scripts](how-to/running-scripts.md) — the scripts in `scripts/` and the `just` recipes that run them
- [Creating Quarto Reports](how-to/creating-quarto-reports.md) — write and render a `.qmd` report offline
- [Cross-Review a Change](how-to/how-to-cross-review-a-change.md) — get a second review from the other AI and keep it on the PR

## Reference

Technical descriptions of each major process and module.

- [Project Structure](reference/project-structure.md) — every directory and what lives in it
- [Fixed-Income Concepts](reference/fixed-income.md) — duration, convexity, DV01, the two-swap hedge, KRD, IRR
- [Credit Spreads & Ratings](reference/credit-spreads.md) — rating scales, spread by rating and maturity, the three fixed-income universes
- [Data Sources](reference/data-sources.md) — where every input comes from: FRED, SOA tables, the assumptions file
- [SPIA](reference/spia.md) — single premium immediate annuity: pricing, cash flows, duration
- [Whole Life](reference/whole-life.md) — whole life insurance: net level premium, cash flows, DV01
- [Term Life](reference/term-life.md) — term life insurance: cash flows, DV01, comparison with whole life
- [FIA](reference/fia.md) — fixed indexed annuity: crediting mechanics, scenarios, sensitivities
- [Immunization with Swaps](reference/immunization-with-swaps.md) — closing DV01 and dollar-convexity gaps with two interest-rate swaps
