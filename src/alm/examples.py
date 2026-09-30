"""The sample insurer used by the lecture deck and the README chart, defined once.

Everything here is illustrative: par-priced bonds, one private loan, one mortgage whole
loan, and three liabilities (whole life, SPIA, FIA) on the SOA 2012 IAM table, all at a
flat 4% Treasury rate.  Assets are carried at their own purchase yield (par at issue);
the spread a risky asset earns over Treasuries is promised excess income, not value.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from alm.asset import Bond, Mortgage, PrivateCredit
from alm.core import InterestRateSwap, dollar_convexity, dv01, immunize
from alm.liability import FIA, SPIA, WL, qx_from_table
from alm.read import get_2012_iam_table, get_spread

Asset = Bond | Mortgage | PrivateCredit


def asset_face(asset: Asset) -> float:
    """Par amount: face value of a bond or loan, original principal of a mortgage."""
    return asset.principal if isinstance(asset, Mortgage) else asset.face_value


def asset_yield(asset: Asset) -> float:
    """Purchase yield: coupon of a par bond, total yield of a private loan, note rate of a mortgage.

    Nominal annual, compounded at the instrument's own frequency.
    """
    if isinstance(asset, PrivateCredit):
        return asset.total_yield
    if isinstance(asset, Mortgage):
        return asset.annual_rate
    return asset.coupon_rate


@dataclass(frozen=True)
class TwoSwapHedge:
    """A DV01 and dollar-convexity matching hedge built from two receive-fixed unit swaps.

    ``notionals`` are signed: positive means receive-fixed, negative means pay-fixed.
    This is the two-instrument surplus hedge for parallel shifts, not Redington
    immunization (which also needs equal present values and asset convexity at or
    above liability convexity).
    """

    tenors: tuple[int, int]
    notionals: tuple[float, float]
    dv01_per_unit: tuple[float, float]
    dconv_per_unit: tuple[float, float]
    positions: tuple[InterestRateSwap, InterestRateSwap]

    @property
    def gross_notional(self) -> float:
        return sum(abs(n) for n in self.notionals)

    def pv(self, r: float) -> float:
        """Value of the sized swaps after a parallel shift to Treasury rate *r*."""
        return sum(p.present_value([r] * p.n_periods, r) for p in self.positions)


@dataclass
class LectureBook:
    """The deck's sample insurer: assets, liabilities, and the valuation rules that tie them."""

    discount_rate: float
    assets: list[Asset]
    labels: list[str]
    classes: list[str]
    ratings: list[str]
    wl: WL
    spia: SPIA
    fia: FIA
    fia_index_returns: list[float]

    # ---- valuation ---------------------------------------------------------

    def asset_pv(self, asset: Asset, shock: float = 0.0) -> float:
        """Value an asset at its own yield plus a parallel shift; par when the shift is zero."""
        return asset.present_value(asset_yield(asset) + shock)

    def pv_assets(self, r: float) -> float:
        """Total asset value when the Treasury rate is *r*: each asset at its own yield + shift."""
        return sum(self.asset_pv(a, r - self.discount_rate) for a in self.assets)

    def asset_pv_func(self, asset: Asset) -> Callable[[float], float]:
        """Single-asset version of :meth:`pv_assets`, for :func:`alm.core.dv01`."""
        return lambda r: self.asset_pv(asset, r - self.discount_rate)

    def fia_pv(self, r: float) -> float:
        """FIA present value on the single index path as a function of the discount rate."""
        return self.fia.present_value(self.fia_index_returns, r)

    def pv_liab_hedged(self, r: float) -> float:
        """WL + SPIA: the fixed-cash-flow liabilities the swap hedge targets."""
        return self.wl.present_value(r) + self.spia.present_value(r)

    def pv_liabilities(self, r: float) -> float:
        """All reserves, with the FIA at its single-path PV (it is outside the rate hedge)."""
        return self.pv_liab_hedged(r) + self.fia_pv(r)

    def balance_sheet(self) -> dict[str, float]:
        """Assets, reserves and surplus at purchase price (the base Treasury rate)."""
        r = self.discount_rate
        wl_pv = self.wl.present_value(r)
        if abs(wl_pv) < 0.005:  # equivalence principle: the net premium reserve is zero at issue
            wl_pv = 0.0
        spia_pv = self.spia.present_value(r)
        fia_pv = self.fia_pv(r)
        assets = self.pv_assets(r)
        liabilities = wl_pv + spia_pv + fia_pv
        return {
            "assets": assets,
            "whole_life": wl_pv,
            "spia": spia_pv,
            "fia": fia_pv,
            "liabilities": liabilities,
            "surplus": assets - liabilities,
        }

    def assets_by_class(self) -> dict[str, float]:
        """Asset value by class at purchase price, in the deck's display order."""
        order = ["Government bonds", "Corporate bonds", "Mortgage loans", "Private credit"]
        totals = dict.fromkeys(order, 0.0)
        for asset, cls in zip(self.assets, self.classes, strict=True):
            totals[cls] += self.asset_pv(asset)
        return totals

    # ---- hedging -----------------------------------------------------------

    def two_swap_hedge(self, tenors: tuple[int, int] = (5, 10)) -> TwoSwapHedge:
        """Size two swaps so the WL + SPIA book has zero DV01 and dollar-convexity gap.

        Per-unit sensitivities come from receive-fixed unit swaps at the base rate with
        floating rates bumped together with the discount rate (a parallel shift), then
        :func:`alm.core.immunize` solves the 2x2 system.
        """
        r = self.discount_rate
        gap_dv01 = dv01(self.pv_liab_hedged, r) - dv01(self.pv_assets, r)
        gap_dconv = dollar_convexity(self.pv_liab_hedged, r) - dollar_convexity(self.pv_assets, r)

        units = [
            InterestRateSwap(notional=1.0, fixed_rate=r, tenor=t, pay_fixed=False) for t in tenors
        ]
        per_dv01 = [swap.dv01([r] * swap.n_periods, r) for swap in units]
        per_dconv = [
            dollar_convexity(lambda x, s=swap: s.present_value([x] * s.n_periods, x), r)
            for swap in units
        ]
        n1, n2 = immunize(gap_dv01, gap_dconv, per_dv01[0], per_dconv[0], per_dv01[1], per_dconv[1])
        positions = tuple(
            InterestRateSwap(notional=abs(n), fixed_rate=r, tenor=t, pay_fixed=n < 0)
            for n, t in zip((n1, n2), tenors, strict=True)
        )
        return TwoSwapHedge(
            tenors=tuple(tenors),
            notionals=(n1, n2),
            dv01_per_unit=(per_dv01[0], per_dv01[1]),
            dconv_per_unit=(per_dconv[0], per_dconv[1]),
            positions=positions,
        )

    def surplus(self, r: float, hedge: TwoSwapHedge | None = None) -> float:
        """Surplus after a parallel shift to Treasury rate *r*, with an optional swap hedge."""
        hedge_pv = hedge.pv(r) if hedge is not None else 0.0
        return self.pv_assets(r) + hedge_pv - self.pv_liabilities(r)


def lecture_book(discount_rate: float = 0.04) -> LectureBook:
    """Build the sample insurer used in the deck.

    Every asset is bought at par with a coupon equal to the Treasury rate plus the spread for
    its rating and maturity from ``assumptions/credit_spreads.csv``; Treasuries (AA+ / Aa1
    since May 2025) define the risk-free curve and carry no spread.  Mortgage whole loans are
    priced off the A curve, as :meth:`alm.core.Block.generate_assets` does.
    """
    spread_a_5y = get_spread("A", 5)
    spread_bb_7y = get_spread("BB", 7)
    spread_a_15y = get_spread("A", 15)
    spread_aa_20y = get_spread("AA", 20)

    assets: list[Asset] = [
        Bond(
            face_value=8_000_000, coupon_rate=discount_rate, maturity=2, frequency=2, rating="AA+"
        ),
        Bond(
            face_value=10_000_000,
            coupon_rate=discount_rate + spread_a_5y,
            maturity=5,
            frequency=2,
            rating="A",
            credit_spread=spread_a_5y,
        ),
        PrivateCredit(
            face_value=5_000_000,
            maturity=7,
            risk_free_rate=discount_rate,
            credit_spread=spread_bb_7y,
            illiquidity_spread=0.020,
            other_spread=0.005,
            rating="BB",
        ),
        Bond(
            face_value=15_000_000, coupon_rate=discount_rate, maturity=10, frequency=2, rating="AA+"
        ),
        Mortgage(principal=4_000_000, annual_rate=discount_rate + spread_a_15y, term=15),
        Bond(
            face_value=8_000_000,
            coupon_rate=discount_rate + spread_aa_20y,
            maturity=20,
            frequency=2,
            rating="AA",
            credit_spread=spread_aa_20y,
        ),
    ]

    mortality = get_2012_iam_table()
    wl = WL.from_face(
        face_value=10_000_000,
        qx=qx_from_table(mortality, age=45, sex="male"),
        discount_rate=discount_rate,
        age=45,
    )
    spia = SPIA.from_payout(
        annual_payout=3_000_000,
        qx=qx_from_table(mortality, age=65, sex="female"),
        discount_rate=discount_rate,
        age=65,
    )
    fia = FIA(
        premium=3_000_000,
        term=10,
        qx=qx_from_table(mortality, age=55, sex="male"),
        floor=0.00,
        cap=0.08,
        participation_rate=0.80,
        age=55,
    )
    # One illustrative equity-index path; the FIA is valued on it and kept out of the rate hedge
    fia_index_returns = [-0.02, 0.06, 0.12, 0.04, -0.05, 0.10, 0.03, 0.08, -0.01, 0.07]

    return LectureBook(
        discount_rate=discount_rate,
        assets=assets,
        labels=[
            "$8M UST 2Y",
            "$10M Corp A 5Y",
            "$5M PC BB 7Y",
            "$15M UST 10Y",
            "$4M Mortgage 15Y",
            "$8M Corp AA 20Y",
        ],
        classes=[
            "Government bonds",
            "Corporate bonds",
            "Private credit",
            "Government bonds",
            "Mortgage loans",
            "Corporate bonds",
        ],
        ratings=["AA+", "A", "BB", "AA+", "A (whole loan)", "AA"],
        wl=wl,
        spia=spia,
        fia=fia,
        fia_index_returns=fia_index_returns,
    )
