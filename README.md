# ALM

Educational toolkit demonstrating Asset-Liability Management (ALM) concepts for actuarial science students. Built as a personal project for illustrative purposes only — not intended for professional use, financial advice, or production decision-making.

## Quick Start

**Prerequisites:** Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/realslimslaney/ALM.git
cd ALM
uv sync
uv run pytest
```

> New to development? See the [Environment Setup](docs/how-to/environment-setup.md) guide for step-by-step instructions.

## Documentation

- [Environment Setup](docs/how-to/environment-setup.md) — install VS Code, Git, Python, uv, and Quarto from scratch
- [Getting Started](docs/how-to/getting-started.md) — clone the repo, install dependencies, and verify
- [Running Scripts](docs/how-to/running-scripts.md) — execute scripts with `uv run`
- [Creating Quarto Reports](docs/how-to/creating-quarto-reports.md) — author and render `.qmd` reports
- [Project Structure](docs/reference/project-structure.md) — repository layout and conventions

## Simplifying Assumptions

This toolkit is built for learning, not production. Several real-world complexities are intentionally omitted:

- **No expenses.** Policy pricing does not include acquisition costs, administrative expenses, or commissions, nor are any assets reserved to cover them.
- **No defaults.** Bond and private credit default rates are assumed to be 0%. Realistic default modeling could produce negative asset returns that break small-sample examples.
- **No liquidity management.** If liability claims come due before asset cash flows mature, the model does not sell assets early, borrow, or rebalance. A real insurer would fail regulatory liquidity standards under this approach.
- **Flat yield curve.** A single `discount_rate` is used for all maturities. Real ALM uses a full term structure of interest rates.
- **No lapses or surrenders.** Policyholders are assumed to hold policies to maturity or death. In practice, lapse rates materially affect liability cash flows and reserve requirements.
- **No reinvestment risk modeling.** When bonds mature and proceeds are reinvested, the model reuses the original discount rate rather than simulating future rate environments.
- **Deterministic mortality.** Mortality follows the table exactly with no stochastic variation. Real portfolios experience mortality volatility, especially in small blocks.
- **No regulatory capital.** The model does not compute or reserve for statutory or risk-based capital requirements (e.g., C-1 through C-4 risks).
- **Simplified premium calculation.** Auto-calculated premiums use `PV(expected benefits) * (1 + profit_margin)` — a rough equivalence principle. Real pricing accounts for expenses, profit targets, lapses, and regulatory reserves.
- **No taxes.** Investment income and underwriting gain are not reduced by federal or state taxes.

## Development

```bash
uv run pre-commit install  # install git hooks (once)
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pytest              # test
```

## License

[MIT](LICENSE)
