# Immunization with Interest Rate Swaps

How to hedge a portfolio's duration and convexity gaps using
plain-vanilla interest rate swaps, as implemented in the ALM toolkit.

---

## The Problem

An insurer holds assets (bonds, mortgages, private credit) backing
liabilities (annuities, life insurance).  If interest rates change,
assets and liabilities reprice by different amounts because they have
different duration and convexity profiles.  The surplus
(Assets − Liabilities) swings unpredictably.

**Goal:**  Make surplus insensitive to parallel shifts in the yield
curve by closing both the duration gap and the convexity gap.

---

## Interest Rate Swaps as Hedging Instruments

A plain-vanilla fixed-for-floating swap exchanges:

- **Fixed leg:** periodic payments at a pre-agreed rate
- **Floating leg:** periodic payments that reset to market rates

| Position | Duration effect | Economic equivalent |
|----------|----------------|---------------------|
| **Receive-fixed** (pay floating) | Adds duration | Long a fixed-rate bond, short a floater |
| **Pay-fixed** (receive floating) | Removes duration | Short a fixed-rate bond, long a floater |

Swaps are off-balance-sheet — they adjust risk without buying or
selling bonds.

**Code:** `InterestRateSwap` in `src/alm/core.py`

---

## Step 1 — Measure the Gaps

### Dollar Duration Gap (DV01)

DV01 measures the dollar change in value for a 1 bp parallel rate
shift:

$$
\text{DV01} = \frac{PV(y - 0.0001) - PV(y + 0.0001)}{2}
$$

The gap to close is:

$$
\Delta\text{DV01} = \text{DV01}_{\text{liabilities}} - \text{DV01}_{\text{assets}}
$$

A positive gap means liabilities are more rate-sensitive than assets —
rates falling would widen the deficit.

**Code:** `dv01()` in `src/alm/core.py`

### Dollar Convexity Gap

Dollar convexity measures how DV01 itself changes as rates move (the
second derivative of PV with respect to yield):

$$
C_\$ = \frac{PV(y + h) + PV(y - h) - 2 \cdot PV(y)}{h^2}
$$

The gap:

$$
\Delta C_\$ = C_{\$,\text{liabilities}} - C_{\$,\text{assets}}
$$

Duration-only hedging leaves the portfolio exposed to large rate moves.
Closing the convexity gap fixes this.

**Code:** `dollar_convexity()` in `src/alm/core.py`

---

## Step 2 — Choose Two Hedging Instruments

You need **two** instruments with linearly independent sensitivity
profiles to target both DV01 and convexity simultaneously.  A short-
tenor and a long-tenor swap work well because:

- Both have non-zero DV01 (from their fixed legs)
- The longer swap has proportionally more convexity
- The ratio of DV01-to-convexity differs between them

| Instrument | Why it works |
|------------|-------------|
| 5-year swap | Lower duration, lower convexity per unit notional |
| 10-year swap | Higher duration, higher convexity per unit notional |

**Important — parallel shift convention for swaps:**  When computing
swap sensitivities, bump the floating rates *and* the discount rate
together.  This reflects a true parallel curve shift.  If you only bump
the discount rate while holding floating rates fixed, an at-par swap
(where fixed rate = floating rate = discount rate) will show zero PV
change and zero convexity, making the hedge matrix singular.

```python
# Correct: floating rates move with the discount rate
dc_5y = dollar_convexity(
    lambda r: swap_5y.present_value([r] * swap_5y.n_periods, r),
    discount_rate,
) / swap_5y.notional

# Wrong: floating rates are frozen — convexity ≈ 0
dc_5y = dollar_convexity(
    lambda r: swap_5y.present_value(flat_floats, r),
    discount_rate,
) / swap_5y.notional
```

---

## Step 3 — Solve the 2×2 System

Given per-unit sensitivities of each hedging instrument, solve for the
notionals $n_1$ and $n_2$:

$$
\begin{bmatrix}
\text{DV01}_1 & \text{DV01}_2 \\
C_{\$,1} & C_{\$,2}
\end{bmatrix}
\begin{bmatrix}
n_1 \\ n_2
\end{bmatrix}
=
\begin{bmatrix}
\Delta\text{DV01} \\
\Delta C_\$
\end{bmatrix}
$$

The solution via Cramer's rule:

$$
n_1 = \frac{\Delta\text{DV01} \cdot C_{\$,2} - \Delta C_\$ \cdot \text{DV01}_2}
           {\text{DV01}_1 \cdot C_{\$,2} - \text{DV01}_2 \cdot C_{\$,1}}
$$

$$
n_2 = \frac{\text{DV01}_1 \cdot \Delta C_\$ - C_{\$,1} \cdot \Delta\text{DV01}}
           {\text{DV01}_1 \cdot C_{\$,2} - \text{DV01}_2 \cdot C_{\$,1}}
$$

The denominator is the determinant of the sensitivity matrix.  If it is
zero (or near-zero), the two instruments are linearly dependent and
cannot independently target both gaps — pick instruments with more
separation in tenor.

**Interpreting the sign of $n$:**

| Sign | Meaning |
|------|---------|
| $n > 0$ | Enter a receive-fixed position of that notional |
| $n < 0$ | Enter a pay-fixed position of $|n|$ notional |

**Code:** `immunize()` in `src/alm/core.py`

---

## Step 4 — Verify Under Stress

After computing the hedge, re-run the portfolio under parallel rate
shocks (e.g. ±100 bp, ±200 bp) and compare surplus with and without
the hedge.  A well-immunized portfolio should show:

- Surplus nearly flat across small shocks (duration matched)
- Surplus slightly *gaining* under large shocks in either direction
  (positive net convexity)

---

## Worked Example

```python
from alm.core import (
    InterestRateSwap, dv01, dollar_convexity, immunize,
)

DISCOUNT_RATE = 0.04

# 1. Measure gaps (computed from your asset/liability portfolio)
asset_dv01 = sum(dv01(a.present_value, DISCOUNT_RATE) for a in assets)
liab_dv01  = sum(dv01(l.present_value, DISCOUNT_RATE) for l in liabilities)
dd_gap = liab_dv01 - asset_dv01

asset_dc = sum(dollar_convexity(a.present_value, DISCOUNT_RATE) for a in assets)
liab_dc  = sum(dollar_convexity(l.present_value, DISCOUNT_RATE) for l in liabilities)
dc_gap = liab_dc - asset_dc

# 2. Define hedging instruments
swap_5y  = InterestRateSwap(notional=1, fixed_rate=0.04, tenor=5,  pay_fixed=False)
swap_10y = InterestRateSwap(notional=1, fixed_rate=0.04, tenor=10, pay_fixed=False)

# 3. Compute per-unit sensitivities (parallel shift convention)
dd_5y  = swap_5y.dv01([0.04] * swap_5y.n_periods, DISCOUNT_RATE)
dc_5y  = dollar_convexity(
    lambda r: swap_5y.present_value([r] * swap_5y.n_periods, r),
    DISCOUNT_RATE,
)
dd_10y = swap_10y.dv01([0.04] * swap_10y.n_periods, DISCOUNT_RATE)
dc_10y = dollar_convexity(
    lambda r: swap_10y.present_value([r] * swap_10y.n_periods, r),
    DISCOUNT_RATE,
)

# 4. Solve
n1, n2 = immunize(dd_gap, dc_gap, dd_5y, dc_5y, dd_10y, dc_10y)
# n1 = notional for the 5Y swap
# n2 = notional for the 10Y swap
```

---

## Common Pitfalls

| Pitfall | Consequence | Fix |
|---------|-------------|-----|
| Only matching DV01 (ignoring convexity) | Surplus exposed to large rate moves | Use two instruments and match both |
| Freezing floating rates when computing swap convexity | Sensitivity matrix is singular (`ValueError`) | Bump floating rates with the discount rate |
| Using two swaps with very similar tenors | Near-singular matrix, unstable notionals | Separate tenors by at least 3–5 years |
| Forgetting to re-hedge after asset/liability changes | Gaps drift over time | Re-run periodically or after material changes |

---

## Quick Reference

| Function | Module | Purpose |
|----------|--------|---------|
| `dv01(pv_func, rate)` | `core` | Dollar duration via central difference |
| `dollar_convexity(pv_func, rate)` | `core` | Dollar convexity via central difference |
| `immunize(dd_gap, dc_gap, ...)` | `core` | Solve 2×2 hedge for notionals |
| `InterestRateSwap` | `core` | Swap cashflows, PV, DV01, convexity |
