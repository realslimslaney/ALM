# Credit Ratings & Spreads Reference

How creditworthiness is measured, how it translates into yield
spreads, and how the three fixed-income universes used in this toolkit
— Treasuries, corporate bonds, and private credit — compare.

---

## Credit Ratings

A credit rating is an opinion on the likelihood that a borrower will
meet its debt obligations.  The two major scales are:

| Quality tier | S&P / Fitch | Moody's | This toolkit |
|---|---|---|---|
| Highest quality | AAA | Aaa | AAA |
| High quality | AA+/AA/AA− | Aa1/Aa2/Aa3 | AA |
| Upper medium | A+/A/A− | A1/A2/A3 | A |
| Medium | BBB+/BBB/BBB− | Baa1/Baa2/Baa3 | BBB |
| Speculative | BB+/BB/BB− | Ba1/Ba2/Ba3 | BB |
| Highly speculative | B+/B/B− | B1/B2/B3 | B |

Everything **BBB / Baa3 and above** is *investment grade* (IG).
Everything below is *high yield* (HY), sometimes called "junk."

The toolkit collapses the notch-level detail (e.g. AA+, AA, AA−) into
a single letter grade for simplicity.

---

## Credit Spread

**What it measures:**  The extra yield an investor demands over the
risk-free rate to compensate for credit risk (and, in some markets,
liquidity risk).

$$
\text{Spread} = y_{\text{bond}} - y_{\text{Treasury}}
$$

Spreads are quoted in **basis points** (bps), where 1 bp = 0.01%.

**Key drivers of spread width:**

| Factor | Effect |
|---|---|
| Lower credit rating | Wider spread |
| Longer maturity | Wider spread (more time for default) |
| Economic stress | Wider spreads across all ratings |
| Illiquidity | Wider spread (private markets) |

---

## The Spread Curve

Spreads vary by both rating and maturity.  The toolkit stores a full
term structure in `assumptions/credit_spreads.csv` (values in bps):

| Rating | 1Y | 2Y | 3Y | 5Y | 7Y | 10Y | 20Y | 30Y |
|---|---|---|---|---|---|---|---|---|
| AAA | 23 | 35 | 46 | 70 | 93 | 116 | 139 | 151 |
| AA | 22 | 32 | 42 | 63 | 82 | 100 | 120 | 131 |
| A | 18 | 27 | 36 | 52 | 64 | 76 | 91 | 97 |
| BBB | 48 | 68 | 87 | 119 | 143 | 167 | 207 | 223 |
| BB | 106 | 141 | 177 | 226 | 262 | 297 | 354 | 375 |
| B | 212 | 264 | 312 | 374 | 418 | 460 | 531 | 552 |

When a bond's maturity falls between table tenors, `get_spread()`
linearly interpolates.

**Code:** `get_spread()` and `get_credit_spreads()` in `src/alm/read.py`

---

## Updating Spreads from Market Data

The spread table can be refreshed from four FRED series that anchor
the 10-year point for specific ratings:

| Rating | FRED anchor | Series ID | Description |
|---|---|---|---|
| AAA | AAA10Y | AAA10Y | Moody's Aaa yield − 10Y Treasury |
| A | IG_OAS | BAMLC0A0CM | ICE BofA US Corporate IG OAS |
| BBB | BAA10Y | BAA10Y | Moody's Baa yield − 10Y Treasury |
| BB | HY_OAS | BAMLH0A0HYM2 | ICE BofA US High Yield OAS |

The update algorithm:

1. Fetch the latest 10Y anchor spread for AAA, A, BBB, BB from FRED
2. Compute a scale factor for each: `new_10Y / old_10Y`
3. Multiply the entire tenor curve for that rating by the scale factor
4. **AA** is interpolated between AAA and A, preserving its original
   relative position between the two
5. **B** is extrapolated from BB, preserving the original BB-to-B ratio
   at each tenor
6. Round to whole basis points and write back to CSV

**Code:** `update_credit_spreads()` in `src/alm/read.py`

---

## Comparing the Three Asset Classes

The toolkit models three fixed-income universes with distinct risk and
return characteristics:

### Treasuries (Government Bonds)

| Attribute | Detail |
|---|---|
| Issuer | U.S. government (sovereign) |
| Credit risk | Effectively zero (AAA / AA rated) |
| Liquidity | Highest — deep, transparent markets |
| Spread over risk-free | Minimal (the Treasury *is* the risk-free benchmark) |
| Typical ratings in toolkit | 70% AAA, 30% AA |
| Role in portfolio | Duration anchor, safe-haven allocation |

Treasuries define the risk-free yield curve.  In this toolkit, the
"discount rate" generally represents a Treasury-level rate, and all
other instruments earn a spread above it.

### Corporate Bonds

| Attribute | Detail |
|---|---|
| Issuer | Corporations (public companies) |
| Credit risk | Moderate — depends on rating |
| Liquidity | Good for IG; lower for HY |
| Spread over risk-free | 50–550+ bps depending on rating and maturity |
| Typical ratings in toolkit | 30% A, 50% BBB, 15% BB, 5% B |
| Role in portfolio | Yield enhancement, diversification |

Corporate bonds are the largest source of credit spread income in a
typical insurance portfolio.  The toolkit tilts toward BBB — the
sweet spot at the bottom of investment grade, where spreads are
meaningfully wider than A-rated debt but default risk remains
relatively contained.

### Private Credit

| Attribute | Detail |
|---|---|
| Issuer | Middle-market companies, project finance, etc. |
| Credit risk | Higher — typically BB / B rated |
| Liquidity | Very low — no secondary market |
| Spread over risk-free | Wide: credit spread + illiquidity premium + other |
| Typical ratings in toolkit | 40% BB, 60% B |
| Role in portfolio | Yield pickup, illiquidity premium capture |
| Regulatory cap | 10% of portfolio (SAA constraint) |

Private credit earns the widest total yield because it compensates for
*both* credit risk and illiquidity.  The toolkit decomposes the total
yield into four components:

$$
y_{\text{total}} = y_{\text{risk-free}} + s_{\text{credit}} + s_{\text{illiquidity}} + s_{\text{other}}
$$

| Component | Toolkit default | Source |
|---|---|---|
| Risk-free rate | Varies (discount rate) | Treasury curve |
| Credit spread | Varies by rating / maturity | `assumptions/credit_spreads.csv` |
| Illiquidity spread | 200 bps (hardcoded) | Industry estimate |
| Other spread | 50 bps (hardcoded) | Catch-all (complexity, structuring) |

**Valuation note:** The `PrivateCredit` class discounts at the
risk-free rate by default (not the total yield).  This means the PV
exceeds par — the excess represents the economic value of the
illiquidity premium to a buy-and-hold investor like an insurer.

**Code:** `PrivateCredit` in `src/alm/asset.py`, `PC_RATING_DIST` in `src/alm/core.py`

---

## Side-by-Side Summary

| | Treasury | Corporate | Private Credit |
|---|---|---|---|
| **Credit quality** | AAA / AA | A to B | BB / B |
| **10Y spread (bps)** | ~0 | 76–460 | 297–460 + 250 illiq/other |
| **Liquidity** | Excellent | Good (IG) / Fair (HY) | Poor |
| **Valuation method** | Discount at yield | Discount at yield | Discount at risk-free rate |
| **Duration behavior** | Standard | Standard | Standard (bullet-like) |
| **SAA weight (default)** | 40% | 30% | 10% |
| **Maturities (default)** | 5, 10, 20, 30Y | 5, 10, 20, 30Y | 3, 5Y |

---

## Rating Distributions

Each asset class in the toolkit has a hardcoded rating distribution
used when generating block-level portfolios:

**Government bonds** (`GOVT_RATING_DIST`):

| Rating | Weight |
|---|---|
| AAA | 70% |
| AA | 30% |

**Corporate bonds** (`CORP_RATING_DIST`):

| Rating | Weight |
|---|---|
| A | 30% |
| BBB | 50% |
| BB | 15% |
| B | 5% |

**Private credit** (`PC_RATING_DIST`):

| Rating | Weight |
|---|---|
| BB | 40% |
| B | 60% |

**Code:** `GOVT_RATING_DIST`, `CORP_RATING_DIST`, `PC_RATING_DIST` in `src/alm/core.py`
