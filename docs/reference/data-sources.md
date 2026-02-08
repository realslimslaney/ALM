# Data Sources Reference

A complete inventory of where every piece of data in the toolkit comes
from — external APIs, published tables, static assumptions files, and
hardcoded estimates.

---

## External Sources (Live Data)

### FRED — Federal Reserve Economic Data

The toolkit fetches market data from the
[FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) via the
`fredapi` Python package.  A free API key is required (set
`FRED_API_KEY` in `.env`).

#### Treasury Yield Curve

US Treasury constant-maturity rates — the risk-free benchmark curve.

| Tenor | FRED Series ID | Description |
|---|---|---|
| 1 Month | DGS1MO | 1-Month Treasury Constant Maturity |
| 3 Month | DGS3MO | 3-Month Treasury Constant Maturity |
| 6 Month | DGS6MO | 6-Month Treasury Constant Maturity |
| 1 Year | DGS1 | 1-Year Treasury Constant Maturity |
| 2 Year | DGS2 | 2-Year Treasury Constant Maturity |
| 3 Year | DGS3 | 3-Year Treasury Constant Maturity |
| 5 Year | DGS5 | 5-Year Treasury Constant Maturity |
| 7 Year | DGS7 | 7-Year Treasury Constant Maturity |
| 10 Year | DGS10 | 10-Year Treasury Constant Maturity |
| 20 Year | DGS20 | 20-Year Treasury Constant Maturity |
| 30 Year | DGS30 | 30-Year Treasury Constant Maturity |

Rates are expressed as **percentages** (e.g. 4.25 means 4.25%).
Daily observations; weekends and holidays have no data.

**Code:** `read_treasury_rates()` in `src/alm/read.py`

**Cached at:** `assumptions/treasury_rates.csv` (auto-fetched on
first call, refreshable via `get_treasury_rates(refresh=True)`)

#### Credit Spread Indices

Used to anchor the credit spread term structure to current market
conditions.

| Label | FRED Series ID | Description |
|---|---|---|
| IG_OAS | BAMLC0A0CM | ICE BofA US Corporate Investment Grade OAS |
| HY_OAS | BAMLH0A0HYM2 | ICE BofA US High Yield OAS |
| BAA10Y | BAA10Y | Moody's Baa Corporate Bond Yield Relative to 10Y Treasury |
| AAA10Y | AAA10Y | Moody's Aaa Corporate Bond Yield Relative to 10Y Treasury |

Spreads are in **percentage points** (e.g. 1.50 means 150 bps).

These four series anchor the 10-year spread for four ratings (AAA, A,
BBB, BB).  The remaining ratings (AA, B) are derived by interpolation
and extrapolation.  See `update_credit_spreads()` in `src/alm/read.py`
for the full algorithm.

**Code:** `read_credit_spread_indices()`, `update_credit_spreads()` in
`src/alm/read.py`

---

### SOA — Society of Actuaries Mortality Tables

#### IAM 2012 Basic Tables

The **Individual Annuity Mortality** 2012 Basic table, published by
the Society of Actuaries.  Used for all life-contingent liability
calculations (SPIA, WL, Term, FIA).

| File | Contents |
|---|---|
| `data/soa_tables/iam_2012_male_basic_anb.csv` | Male mortality rates by age |
| `data/soa_tables/iam_2012_female_basic_anb.csv` | Female mortality rates by age |

**Format:** Two columns — `age` (integer) and `male` or `female`
(the one-year mortality probability $q_x$, as a decimal).
Age-nearest-birthday (ANB) basis.

**Usage:**
- `read_mortality_table("male")` / `read_mortality_table("female")`
  reads a single table
- `get_2012_iam_table()` combines both into a long-format DataFrame
  with columns: `age`, `sex`, `qx`
- `qx_from_table(table, age, sex)` extracts the $q_x$ vector from a
  given issue age to the end of the table

**Mortality assumption within each year:** Uniform Distribution of
Deaths (UDD) — the survival probability at fractional year $t$ is:

$$
{}_tS_x = {}_{\lfloor t \rfloor}S_x \cdot (1 - (t - \lfloor t \rfloor) \cdot q_{x + \lfloor t \rfloor})
$$

**Code:** `read_mortality_table()`, `get_2012_iam_table()` in
`src/alm/read.py`; `qx_from_table()`, `_survival_prob()` in
`src/alm/liability.py`

---

## Static Assumption Files

Stored in the `assumptions/` directory.  These are versioned alongside
the code and can be refreshed from market data.

### Credit Spread Curve

**File:** `assumptions/credit_spreads.csv`

A term structure of credit spreads by rating, in **basis points**.
Columns: `rating`, plus one column per maturity year (`1`, `2`, `3`,
`5`, `7`, `10`, `20`, `30`).

Ratings: AAA, AA, A, BBB, BB, B.

This file is the single source of truth for spread lookups in the
toolkit.  It can be updated from FRED via `update_credit_spreads()`,
or edited manually.

**Code:** `get_credit_spreads()`, `get_spread()` in `src/alm/read.py`

### Treasury Rate Cache

**File:** `assumptions/treasury_rates.csv`

A cached snapshot of the full Treasury yield curve history fetched
from FRED.  Created automatically on first call to
`get_treasury_rates()`.

---

## Hardcoded Assumptions & Estimates

These values are embedded directly in the source code.  They are
reasonable defaults for an educational toolkit but are not derived
from market data.

### Private Credit Spreads

| Parameter | Value | Location |
|---|---|---|
| Illiquidity spread | 200 bps (0.020) | `Block.generate_assets()`, `Block.reinvest()` in `src/alm/core.py` |
| Other spread | 50 bps (0.005) | `Block.generate_assets()`, `Block.reinvest()` in `src/alm/core.py` |

**Rationale:** Industry estimates for middle-market private credit.
The illiquidity premium compensates buy-and-hold investors (like
insurers) for the absence of a liquid secondary market.  The "other"
spread captures complexity and structuring premiums.

### Liability Pricing Parameters

| Parameter | Value | Location |
|---|---|---|
| Profit margin | 5% | `Block.profit_margin` default in `src/alm/core.py` |
| SPIA annual payout rate | 6% of premium | `Block.generate_policies()` in `src/alm/core.py` |
| WL annual premium rate | 1.5% of face value | `Block.generate_policies()` in `src/alm/core.py` |
| Term annual premium rate | 0.5% of face value | `Block.generate_policies()` in `src/alm/core.py` |
| Term policy term | 20 years | `Block.generate_policies()` in `src/alm/core.py` |
| FIA accumulation term | 10 years | `Block.generate_policies()` in `src/alm/core.py` |
| FIA floor | 0% | `FIA` default in `src/alm/liability.py` |
| FIA cap | 6% | `FIA` default in `src/alm/liability.py` |
| FIA participation rate | 100% | `FIA` default in `src/alm/liability.py` |

**Rationale:** Simplified pricing assumptions appropriate for an
educational demonstration.  Real-world pricing would use experience
studies, lapse assumptions, and more granular expense loads.

### Mortgage Assumptions

| Parameter | Value | Location |
|---|---|---|
| Term split | 50% 15-year, 50% 30-year | `Block.generate_assets()` in `src/alm/core.py` |
| Spread proxy | A-rated credit spread at matching maturity | `Block.generate_assets()` in `src/alm/core.py` |
| Reinvestment term | 15 years | `Block.reinvest()` in `src/alm/core.py` |

**Rationale:** Simplified mortgage model with no prepayment.  Uses the
A-rated credit spread as a proxy for the mortgage-Treasury spread,
which is a rough but reasonable approximation.

### Rating Distributions

Hardcoded allocation weights within each asset class.

| Asset class | Distribution | Location |
|---|---|---|
| Government bonds | 70% AAA, 30% AA | `GOVT_RATING_DIST` in `src/alm/core.py` |
| Corporate bonds | 30% A, 50% BBB, 15% BB, 5% B | `CORP_RATING_DIST` in `src/alm/core.py` |
| Private credit | 40% BB, 60% B | `PC_RATING_DIST` in `src/alm/core.py` |

### Strategic Asset Allocations (SAA)

Three predefined allocations, all with a 10% private credit cap:

| SAA | Govt | Corp | Mortgages | PC | Intended for |
|---|---|---|---|---|---|
| `default_saa()` | 40% | 30% | 20% | 10% | General purpose |
| `spia_saa()` | 50% | 30% | 10% | 10% | SPIA (longer duration) |
| `term_saa()` | 30% | 30% | 30% | 10% | Term (shorter duration) |

### Maturity Profiles by Liability Type

Bond maturities chosen to roughly match the liability's duration
profile:

| Liability type | Bond maturities | PC maturities |
|---|---|---|
| SPIA | 5, 10, 20, 30 years | 3, 5 years |
| WL | 5, 10, 20, 30 years | 3, 5 years |
| Term | 3, 5, 10 years | 3, 5 years |
| FIA | 3, 5, 7, 10 years | 3, 5 years |

### Demonstration Script Parameters

Values used in `scripts/run_alm_demonstration.py`:

| Parameter | Value |
|---|---|
| Discount rate | 4% |
| Number of policies per block | 100 |
| Gender split | 50/50 male/female |
| Random seed | 42 |
| SPIA block: age range, total amount | 65–80, $2B |
| WL block: age range, total amount | 30–50, $1B |
| Term block: age range, total amount | 35–55, $5B |
| FIA block: age range, total amount | 50–65, $500M |
| FIA index returns | Simulated: Normal(mean=5%, stdev=10%) |

The FIA index returns are **entirely simulated** — they do not come
from any market data source.  They represent hypothetical annual
returns on an equity index used for crediting rate calculations.

---

## Summary: What's Real vs. What's Estimated

| Data | Source | Refreshable? |
|---|---|---|
| Treasury yield curve | FRED (live API) | Yes — `get_treasury_rates(refresh=True)` |
| Credit spread 10Y anchors | FRED (live API) | Yes — `update_credit_spreads()` |
| Credit spread term structure | Scaled from FRED anchors | Yes — via `update_credit_spreads()` |
| Mortality rates ($q_x$) | SOA IAM 2012 Basic (published) | No — static published table |
| Illiquidity spread (200 bps) | Industry estimate | No — hardcoded |
| Other spread (50 bps) | Estimate | No — hardcoded |
| Liability pricing (payout/premium rates) | Simplified assumptions | No — hardcoded |
| Rating distributions | Stylized allocation | No — hardcoded |
| FIA index returns | Simulated (Normal distribution) | No — generated at runtime |
| SAA weights | Stylized allocation | No — hardcoded |
