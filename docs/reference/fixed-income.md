# Fixed-Income Reference

Definitions, formulas, and worked examples for the core fixed-income
concepts used throughout the ALM toolkit.

---

## Duration (Macaulay)

**What it measures:**  The weighted-average time until a bond's cash
flows are received, where each weight is the present value of that
cash flow as a fraction of the bond's total price.

**Formula:**

$$
D = \frac{1}{P} \sum_{t=1}^{n} \frac{t}{f} \cdot \frac{CF_t}{(1 + y/f)^t}
$$

| Symbol | Meaning |
|--------|---------|
| $P$ | Bond price (present value) |
| $CF_t$ | Cash flow at period $t$ |
| $y$ | Annual yield (discount rate) |
| $f$ | Payment frequency per year |
| $n$ | Total number of periods |

**Interpretation:**  A duration of 4.5 years means the bond's price
behaves like a zero-coupon bond maturing in 4.5 years.  Higher
duration = greater interest-rate sensitivity.

**Mini example — 5-year, 4 % semi-annual bond ($100 par):**

| Period | Year | Cash Flow | PV @ 4 % | Weight | Year $\times$ Weight |
|--------|------|-----------|----------|--------|----------------------|
| 1 | 0.5 | $2.00 | $1.96 | 0.0196 | 0.010 |
| 2 | 1.0 | $2.00 | $1.92 | 0.0192 | 0.019 |
| ... | ... | ... | ... | ... | ... |
| 10 | 5.0 | $102.00 | $83.78 | 0.8378 | 4.189 |
| **Total** | | | **$100.00** | **1.0000** | **$D \approx 4.56$ yrs** |

**Code:** `Bond.duration()` in `src/alm/asset.py`

---

## Modified Duration

**What it measures:**  The percentage price change for a 1 % change in
yield.  Converts Macaulay duration into a direct risk measure.

**Formula:**

$$
D_{\text{mod}} = \frac{D}{1 + y/f}
$$

**Interpretation:**  If $D_{\text{mod}} = 4.47$, a 1 % (100 bp) rise
in yield causes approximately a 4.47 % drop in price.

**Relationship to DV01:**

$$
D_{\text{mod}} = \frac{\text{DV01} \times 10{,}000}{P}
$$

---

## Convexity

**What it measures:**  The curvature of the price-yield relationship —
how duration itself changes as rates move.

**Formula:**

$$
C = \frac{1}{P \cdot f^2} \sum_{t=1}^{n} \frac{t(t+1) \cdot CF_t}{(1 + y/f)^{t+2}}
$$

**Interpretation:**  Convexity is always positive for option-free
bonds.  Higher convexity means:

- Price rises **more** than duration predicts when rates fall
- Price falls **less** than duration predicts when rates rise

This asymmetry is valuable — all else equal, investors prefer higher
convexity.

**Second-order price approximation:**

$$
\frac{\Delta P}{P} \approx -D_{\text{mod}} \cdot \Delta y
  + \tfrac{1}{2} \cdot C \cdot (\Delta y)^2
$$

**Mini example — 5-year, 4 % semi-annual bond ($100 par, $y = 4\%$):**

| | Duration only | Duration + Convexity |
|---|---|---|
| Rates $+1\%$ | $-4.47\%$ | $-4.47\% + 0.11\% = -4.36\%$ |
| Rates $-1\%$ | $+4.47\%$ | $+4.47\% + 0.11\% = +4.58\%$ |

The convexity term ($+0.11\%$) always helps — it dampens losses and
amplifies gains.

**Code:** `Bond.convexity()` in `src/alm/asset.py`

---

## DV01 (Dollar Value of a Basis Point)

**What it measures:**  The dollar change in a position's value for a
one-basis-point (0.01 %) parallel shift in rates.

**Formula (central finite difference):**

$$
\text{DV01} = \frac{PV(y - 0.0001) - PV(y + 0.0001)}{2}
$$

**Interpretation:**  If DV01 = \$45,000 on a \$100M bond, a 1 bp rate
increase reduces value by roughly \$45,000.

**Mini example:**

| | PV |
|---|---|
| Rate = 3.99 % | \$100,044,500 |
| Rate = 4.01 % | \$99,955,500 |
| **DV01** | **\$44,500** |

DV01 is the primary metric for measuring and hedging interest-rate
risk at the portfolio level.  Matching asset and liability DV01s is
the first step in immunization.

**Code:** `dv01()` in `src/alm/core.py`

---

## Key Rate Duration (KRD)

**What it measures:**  The sensitivity of a bond's price to a shift at
a single point on the yield curve, holding all other rates fixed.
KRDs decompose overall duration into contributions from specific
maturities.

**Formula:**

$$
\text{KRD}_k = -\frac{1}{P} \cdot \frac{\Delta P}{\Delta y_k}
$$

where $\Delta y_k$ is a bump at tenor $k$ only (typically 1 bp),
interpolated to nearby cash-flow dates.

**Key properties:**

- KRDs across all tenors sum to the bond's effective duration
- A bullet bond has KRD concentrated at its maturity
- A mortgage or amortizing bond has KRD spread across many tenors

**Mini example — 10-year bullet bond:**

| Tenor | KRD |
|-------|-----|
| 1Y | 0.04 |
| 2Y | 0.04 |
| 5Y | 0.07 |
| 10Y | 7.65 |
| 30Y | 0.00 |
| **Total** | **$\approx$ 7.80** |

Nearly all the rate sensitivity sits at the 10-year point, as
expected for a bullet bond.

**Why it matters:**  KRD analysis reveals mismatches that parallel
duration hedging misses.  A portfolio can be duration-matched overall
but have significant exposure to curve twists (e.g. short end rallies,
long end sells off).

---


## Immunization

**What it measures:**  A hedging strategy that protects a portfolio's
surplus (assets minus liabilities) against parallel shifts in interest
rates by matching both duration and convexity.

### Duration Matching (First Order)

Match the dollar duration of assets to liabilities:

$$
\text{DV01}_{\text{assets}} = \text{DV01}_{\text{liabilities}}
$$

This neutralizes the portfolio against small parallel rate shifts.

### Convexity Matching (Second Order)

Duration matching alone leaves the portfolio exposed to large rate
moves.  Adding a convexity match closes this gap:

$$
C_{\$,\text{assets}} = C_{\$,\text{liabilities}}
$$

where $C_\$$ is dollar convexity.

### Two-Instrument Immunization

With two hedging instruments (e.g. a 5-year and 10-year swap), solve
the 2$\times$2 system:

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

where $\Delta\text{DV01}$ and $\Delta C_\$$ are the gaps to close,
and $n_1, n_2$ are the required notionals.

**Mini example:**

| | DV01 per unit | Dollar Convexity per unit |
|---|---|---|
| 5yr Swap | 4.0 | 20 |
| 10yr Swap | 8.0 | 90 |
| **Gap to close** | **500** | **80,000** |

Solving: $n_1 \approx -4{,}375$, $n_2 \approx 2{,}281$ (receive-fixed
on the 10yr, pay-fixed on the 5yr).

**Code:** `immunize()` in `src/alm/core.py`

---


## IRR (Internal Rate of Return)

**What it measures:**  The discount rate that makes the net present
value of a series of cash flows equal to zero.

**Formula:**

$$
\sum_{t=0}^{n} \frac{CF_t}{(1 + r)^t} = 0
$$

Solve for $r$.  There is no closed-form solution — the ALM toolkit
uses Newton-Raphson iteration.

**Newton-Raphson step:**

$$
r_{k+1} = r_k - \frac{NPV(r_k)}{NPV'(r_k)}
$$

where $NPV'(r) = \sum_{t=0}^{n} \frac{-t \cdot CF_t}{(1+r)^{t+1}}$.

**Mini example — \$100 investment returning \$30/yr for 4 years:**

| Year | Cash Flow |
|------|-----------|
| 0 | $-100$ |
| 1 | $+30$ |
| 2 | $+30$ |
| 3 | $+30$ |
| 4 | $+30$ |

Setting $NPV = 0$: $-100 + 30 \cdot \frac{1-(1+r)^{-4}}{r} = 0$

Solving: $r \approx 7.71\%$

**Code:** `irr()` in `src/alm/core.py`

---

## Quick Reference Table

| Metric | Units | What it answers | First or second order? |
|--------|-------|-----------------|------------------------|
| Duration | Years | How sensitive is price to a rate change? | First |
| Convexity | Years$^2$ | How does duration change as rates move? | Second |
| DV01 | Dollars | What is the dollar impact of 1 bp? | First |
| KRD | Years | Where on the curve does the risk sit? | First |
| IRR | % | What return does this investment earn? | N/A |
