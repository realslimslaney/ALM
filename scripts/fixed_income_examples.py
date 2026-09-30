"""Compute every number printed in ``docs/reference/fixed-income.md``.

Run with ``uv run python scripts/fixed_income_examples.py`` (no network).  Each block prints
the inputs and outputs of one worked example on that page so the page is corrected from this
output rather than typed by hand.  All bonds and swaps use the toolkit's own classes, so the
figures agree with ``alm.asset`` and ``alm.core`` by construction.
"""

from __future__ import annotations

from collections.abc import Callable

from alm.asset import Bond
from alm.core import InterestRateSwap, dollar_convexity, dv01, immunize, irr

YIELD = 0.04  # flat annual yield, nominal compounded semi-annually
SHOCK = 0.01  # 100 bp parallel shift used in the duration/convexity approximation
BP = 0.0001


def section(title: str) -> None:
    print(f"\n== {title} ==")


def print_duration_table(bond: Bond, rate: float) -> None:
    """Print the per-period rows behind the Macaulay duration table."""
    r = rate / bond.frequency
    price = bond.present_value(rate)
    cf = bond.cashflows()
    print(f"{'period':>6} {'year':>5} {'cash flow':>10} {'PV':>8} {'weight':>7} {'yr x w':>7}")
    for t, total in zip(cf["period"], cf["total"], strict=True):
        pv = total / (1 + r) ** t
        weight = pv / price
        year = t / bond.frequency
        print(f"{t:>6} {year:>5.1f} {total:>10.2f} {pv:>8.2f} {weight:>7.4f} {year * weight:>7.3f}")
    print(f"{'total':>6} {'':>5} {'':>10} {price:>8.2f} {1.0:>7.4f} {bond.duration(rate):>7.3f}")


def swap_pv_func(swap: InterestRateSwap) -> Callable[[float], float]:
    """PV of a swap as a function of one flat rate (floating and discount rates move together)."""
    n = swap.n_periods
    return lambda r: swap.present_value([r] * n, r)


def bond_examples() -> None:
    bond = Bond(face_value=100.0, coupon_rate=YIELD, maturity=5)
    price = bond.present_value(YIELD)
    macaulay = bond.duration(YIELD)
    modified = macaulay / (1 + YIELD / bond.frequency)
    convexity = bond.convexity(YIELD)

    section("Macaulay duration: 5-year 4% semi-annual bond, $100 par, y = 4%")
    print_duration_table(bond, YIELD)
    print(f"price                 {price:.2f}")
    print(f"Macaulay duration     {macaulay:.2f} years")

    section("Modified duration")
    print(f"modified duration     {modified:.2f}")
    bond_dv01 = dv01(bond.present_value, YIELD)
    print(f"DV01 x 10,000 / P     {bond_dv01 * 10_000 / price:.2f}  (finite-difference check)")

    section("Convexity and the second-order approximation (+/-100 bp)")
    print(f"convexity             {convexity:.2f} years^2")
    for dy in (SHOCK, -SHOCK):
        first = -modified * dy
        second = 0.5 * convexity * dy**2
        exact = bond.present_value(YIELD + dy) / price - 1
        print(
            f"rates {dy:+.0%}: duration only {first:+.2%}, convexity term {second:+.2%}, "
            f"sum {first + second:+.2%}, exact repricing {exact:+.2%}"
        )

    section("DV01: $100M 5-year 4% semi-annual par bond")
    big = Bond(face_value=100_000_000.0, coupon_rate=YIELD, maturity=5)
    print(f"PV at {YIELD - BP:.2%}           {big.present_value(YIELD - BP):,.0f}")
    print(f"PV at {YIELD + BP:.2%}           {big.present_value(YIELD + BP):,.0f}")
    print(f"DV01                  {dv01(big.present_value, YIELD):,.0f}")


def hedge_example() -> None:
    section("Two-swap DV01 + dollar-convexity matching")
    swaps = {
        tenor: InterestRateSwap(notional=1.0, fixed_rate=YIELD, tenor=tenor, pay_fixed=False)
        for tenor in (5, 10)
    }
    per_unit: dict[int, tuple[float, float]] = {}
    for tenor, swap in swaps.items():
        dd = swap.dv01([YIELD] * swap.n_periods, YIELD)
        dc = dollar_convexity(swap_pv_func(swap), YIELD)
        per_unit[tenor] = (dd, dc)
        print(
            f"{tenor:>2}y receive-fixed swap, unit notional: DV01 {dd:.3e}  "
            f"dollar convexity {dc:.2f}  ratio {dc / dd:,.0f}"
        )

    liabilities = Bond(face_value=100_000_000.0, coupon_rate=YIELD, maturity=10)
    assets = Bond(face_value=100_000_000.0, coupon_rate=YIELD, maturity=7)
    dd_liab = dv01(liabilities.present_value, YIELD)
    dd_asset = dv01(assets.present_value, YIELD)
    dc_liab = dollar_convexity(liabilities.present_value, YIELD)
    dc_asset = dollar_convexity(assets.present_value, YIELD)
    print(f"liability proxy: $100M {liabilities.maturity}-year 4% bond   ", end="")
    print(f"DV01 {dd_liab:,.0f}  dollar convexity {dc_liab:,.0f}")
    print(f"assets:          $100M {assets.maturity}-year 4% bond    ", end="")
    print(f"DV01 {dd_asset:,.0f}  dollar convexity {dc_asset:,.0f}")
    dd_gap = dd_liab - dd_asset
    dc_gap = dc_liab - dc_asset
    print(f"gap (liabilities - assets): DV01 {dd_gap:,.0f}  dollar convexity {dc_gap:,.0f}")

    (dd1, dc1), (dd2, dc2) = per_unit[5], per_unit[10]
    n1, n2 = immunize(dd_gap, dc_gap, dd1, dc1, dd2, dc2)
    print(f"notional 5y  {n1:,.0f}  ({'receive' if n1 > 0 else 'pay'}-fixed)")
    print(f"notional 10y {n2:,.0f}  ({'receive' if n2 > 0 else 'pay'}-fixed)")
    print(f"check DV01:             {n1 * dd1 + n2 * dd2:,.0f} vs gap {dd_gap:,.0f}")
    print(f"check dollar convexity: {n1 * dc1 + n2 * dc2:,.0f} vs gap {dc_gap:,.0f}")

    pv5, pv10 = swap_pv_func(swaps[5]), swap_pv_func(swaps[10])
    for dy in (SHOCK, -SHOCK):
        r = YIELD + dy
        unhedged = assets.present_value(r) - liabilities.present_value(r)
        hedged = unhedged + n1 * pv5(r) + n2 * pv10(r)
        print(f"surplus change for {dy:+.0%}: unhedged {unhedged:,.0f}  hedged {hedged:,.0f}")


def irr_example() -> None:
    section("IRR: -100 then +30 for 4 years")
    print(f"IRR                   {irr([-100, 30, 30, 30, 30]):.2%}")


def main() -> None:
    bond_examples()
    hedge_example()
    irr_example()


if __name__ == "__main__":
    main()
