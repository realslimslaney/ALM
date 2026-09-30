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
| AAA | 8 | 13 | 17 | 25 | 34 | 42 | 50 | 55 |
| AA | 14 | 20 | 26 | 38 | 50 | 61 | 73 | 80 |
| A | 17 | 25 | 34 | 49 | 60 | 71 | 85 | 91 |
| BBB | 29 | 42 | 53 | 73 | 87 | 102 | 127 | 136 |
| BB | 65 | 87 | 109 | 139 | 161 | 183 | 218 | 231 |
| B | 142 | 178 | 209 | 251 | 280 | 309 | 356 | 370 |

When a bond's maturity falls between table tenors, `get_spread()`
linearly interpolates.

**Code:** `get_spread()` and `get_credit_spreads()` in `src/alm/read.py`

---

## Updating Spreads from Market Data

The spread table is refreshed with `just refresh-spreads` from six FRED
series, one per rating, that anchor the 10-year point of each curve:

| Rating | FRED anchor | Series ID | Description |
|---|---|---|---|
| AAA | AAA_OAS | BAMLC0A1CAAA | ICE BofA AAA US Corporate OAS |
| AA | AA_OAS | BAMLC0A2CAA | ICE BofA AA US Corporate OAS |
| A | A_OAS | BAMLC0A3CA | ICE BofA Single-A US Corporate OAS |
| BBB | BBB_OAS | BAMLC0A4CBBB | ICE BofA BBB US Corporate OAS |
| BB | BB_OAS | BAMLH0A1HYBB | ICE BofA BB US High Yield OAS |
| B | B_OAS | BAMLH0A2HYB | ICE BofA Single-B US High Yield OAS |

The update algorithm:

1. Fetch the latest value of each rating's OAS series from FRED
2. Compute a scale factor for each rating: `new_10Y / old_10Y`
3. Multiply the entire tenor curve for that rating by the scale factor,
   which preserves the stylized term-structure shape
4. Round to whole basis points and write back to CSV

All six anchors come from one index family with one methodology, so the
table is ordered (AAA narrowest, B widest) at every tenor. An earlier
version mixed Moody's yield-minus-Treasury series (which include term
premium) with ICE OAS indices and produced an inverted table; the update
now logs a warning if the market data ever breaks the ordering.

Reports and scripts never call the refresh: they read the committed CSV,
so a render is reproducible and needs no FRED key.

**Code:** `update_credit_spreads()` in `src/alm/read.py`

---

## Comparing the Three Asset Classes

The toolkit models three fixed-income universes with distinct risk and
return characteristics:

### Treasuries (Government Bonds)

| Attribute | Detail |
|---|---|
| Issuer | U.S. government (sovereign) |
| Credit risk | Effectively zero; rated AA+ (S&P, Fitch) and Aa1 (Moody's) since May 2025 |
| Liquidity | Highest — deep, transparent markets |
| Spread over risk-free | Zero (the Treasury *is* the risk-free benchmark) |
| Rating label in toolkit | AA+ |
| Role in portfolio | Duration anchor, liquidity, safe-haven allocation |

Treasuries define the risk-free yield curve.  In this toolkit the
"discount rate" is a Treasury-level rate; government bonds earn exactly
that rate and all other instruments earn a spread above it.

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
| Allocation cap | 10% of portfolio (a stylized SAA constraint in this toolkit, not a regulation) |

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

**Valuation note:** The `PrivateCredit` class values the loan at its
own total yield by default, so it is worth par at issue.  The spread
over Treasuries is *expected excess income* to a buy-and-hold investor
(before default losses, which this toolkit ignores), not a day-one
gain; discounting the promised coupons at the risk-free rate would
inflate the asset by the full spread and overstate surplus.

**Code:** `PrivateCredit` in `src/alm/asset.py`, `PC_RATING_DIST` in `src/alm/core.py`

---

## Side-by-Side Summary

| | Treasury | Corporate | Private Credit |
|---|---|---|---|
| **Credit quality** | AA+ / Aa1 | A to B | BB / B |
| **10Y spread (bps)** | 0 | see table above | BB and B spreads + 250 illiq/other |
| **Liquidity** | Excellent | Good (IG) / Fair (HY) | Poor |
| **Valuation method** | Discount at own yield | Discount at own yield | Discount at own yield |
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
| AA+ (US Treasury, zero spread) | 100% |

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
