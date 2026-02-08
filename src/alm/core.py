"""Core ALM instruments and hedging utilities."""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field

import polars as pl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Portfolio-level hedging utilities
# ---------------------------------------------------------------------------


def dv01(pv_func: Callable[[float], float], rate: float, bump: float = 0.0001) -> float:
    """Dollar value of a one-basis-point parallel rate shift.

    Parameters
    ----------
    pv_func : Callable[[float], float]
        A function that returns present value given an annual discount rate.
        For instruments whose PV depends on additional arguments (e.g. a swap
        needing floating rates), use ``functools.partial`` or a lambda to
        create a single-argument wrapper.
    rate : float
        Current annual discount rate as a decimal.
    bump : float
        Rate perturbation in decimal (default 0.0001 = 1 bp).

    Returns
    -------
    float
        Positive means the position gains value when rates fall by 1 bp.
    """
    return (pv_func(rate - bump) - pv_func(rate + bump)) / 2


def dollar_convexity(pv_func: Callable[[float], float], rate: float, bump: float = 0.0001) -> float:
    """Dollar convexity via central finite difference.

    Measures how DV01 itself changes as rates move — the second-order
    price sensitivity.  Used together with :func:`dv01` for convexity
    hedging.

    Parameters
    ----------
    pv_func : Callable[[float], float]
        Present-value function (same contract as :func:`dv01`).
    rate : float
        Current annual discount rate as a decimal.
    bump : float
        Rate perturbation in decimal (default 0.0001 = 1 bp).

    Returns
    -------
    float
        Dollar convexity ≈ d²PV / dy².  Positive for plain option-free
        fixed-income instruments.
    """
    return (pv_func(rate + bump) + pv_func(rate - bump) - 2 * pv_func(rate)) / bump**2


def immunize(
    dd_gap: float,
    dc_gap: float,
    dd_per_unit_1: float,
    dc_per_unit_1: float,
    dd_per_unit_2: float,
    dc_per_unit_2: float,
) -> tuple[float, float]:
    """Solve for notionals of two hedging instruments to close both
    duration and convexity gaps simultaneously.

    Sets up and solves the 2×2 linear system:

    .. math::

        n_1 \\cdot dd_1 + n_2 \\cdot dd_2 = \\Delta DD

        n_1 \\cdot dc_1 + n_2 \\cdot dc_2 = \\Delta DC

    where *ΔDD* and *ΔDC* are the dollar-duration and dollar-convexity
    gaps that the hedge must fill.

    Parameters
    ----------
    dd_gap : float
        Dollar-duration gap to close (DV01_liabilities − DV01_assets).
    dc_gap : float
        Dollar-convexity gap to close
        (dollar_convexity_liabilities − dollar_convexity_assets).
    dd_per_unit_1 : float
        DV01 of hedging instrument 1 per unit notional.
    dc_per_unit_1 : float
        Dollar convexity of hedging instrument 1 per unit notional.
    dd_per_unit_2 : float
        DV01 of hedging instrument 2 per unit notional.
    dc_per_unit_2 : float
        Dollar convexity of hedging instrument 2 per unit notional.

    Returns
    -------
    tuple[float, float]
        ``(notional_1, notional_2)`` — required notionals for each
        hedging instrument.

    Raises
    ------
    ValueError
        If the two instruments have linearly dependent sensitivities
        (determinant ≈ 0), meaning they cannot independently target both
        duration and convexity.

    Examples
    --------
    >>> # 5-year and 10-year swaps closing a duration + convexity gap
    >>> n1, n2 = immunize(
    ...     dd_gap=500, dc_gap=80_000,
    ...     dd_per_unit_1=4.0, dc_per_unit_1=20.0,
    ...     dd_per_unit_2=8.0, dc_per_unit_2=90.0,
    ... )
    """
    det = dd_per_unit_1 * dc_per_unit_2 - dd_per_unit_2 * dc_per_unit_1
    if abs(det) < 1e-15:
        raise ValueError(
            "Hedging instruments have linearly dependent sensitivities; "
            "cannot solve for both duration and convexity. "
            "Choose instruments with different duration/convexity profiles."
        )
    n1 = (dd_gap * dc_per_unit_2 - dc_gap * dd_per_unit_2) / det
    n2 = (dd_per_unit_1 * dc_gap - dc_per_unit_1 * dd_gap) / det
    return n1, n2


def irr(
    cashflows: list[float], guess: float = 0.05, tol: float = 1e-10, max_iter: int = 200
) -> float:
    """Internal rate of return via Newton-Raphson.

    Finds the discount rate *r* such that the net present value of
    *cashflows* equals zero:

    .. math::

        \\sum_{t=0}^{n} \\frac{CF_t}{(1 + r)^t} = 0

    Parameters
    ----------
    cashflows : list[float]
        Annual cash flows where ``cashflows[0]`` is typically the initial
        outlay (negative) and subsequent entries are future receipts.
    guess : float
        Starting estimate for *r* (default 0.05 = 5 %).
    tol : float
        Convergence tolerance on the rate step size (default 1e-10).
    max_iter : int
        Maximum Newton-Raphson iterations (default 200).

    Returns
    -------
    float
        The IRR as a decimal (e.g. 0.08 = 8 %).

    Raises
    ------
    ValueError
        If the algorithm does not converge within *max_iter* iterations.
    """
    r = guess
    for _ in range(max_iter):
        npv = sum(cf / (1 + r) ** t for t, cf in enumerate(cashflows))
        dnpv = sum(-t * cf / (1 + r) ** (t + 1) for t, cf in enumerate(cashflows))
        if abs(dnpv) < 1e-15:
            break
        step = npv / dnpv
        r -= step
        if abs(step) < tol:
            return r
    raise ValueError(f"IRR did not converge after {max_iter} iterations (last r={r:.6f})")


# ---------------------------------------------------------------------------
# Rating distributions per asset class
# ---------------------------------------------------------------------------

GOVT_RATING_DIST: dict[str, float] = {"AAA": 0.70, "AA": 0.30}
CORP_RATING_DIST: dict[str, float] = {"A": 0.30, "BBB": 0.50, "BB": 0.15, "B": 0.05}
PC_RATING_DIST: dict[str, float] = {"BB": 0.40, "B": 0.60}


# ---------------------------------------------------------------------------
# Strategic Asset Allocation
# ---------------------------------------------------------------------------


@dataclass
class SAA:
    """Strategic Asset Allocation.

    Represents target allocation weights for a block of business.
    Weights must sum to 1.0 and private credit cannot exceed 10%.

    Parameters
    ----------
    weights : dict[str, float]
        Mapping of asset class names to weight percentages as
        decimals (e.g. 0.40 for 40 %).  Must sum to 1.0.
    """

    weights: dict[str, float]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"SAA weights must sum to 1.0, got {total:.6f}")
        for name, w in self.weights.items():
            if w < 0:
                raise ValueError(f"SAA weight for '{name}' is negative: {w}")
        pc_weight = self.weights.get("private_credit", 0.0)
        if pc_weight > 0.10 + 1e-9:
            raise ValueError(f"Private credit allocation ({pc_weight:.1%}) exceeds 10% maximum")

    def allocation(self, total_amount: float) -> dict[str, float]:
        """Dollar amounts per asset class."""
        return {k: v * total_amount for k, v in self.weights.items()}


def default_saa() -> SAA:
    """Default SAA: 40% govt, 30% corp, 20% mortgages, 10% PC."""
    return SAA(
        weights={
            "govt_bonds": 0.40,
            "corp_bonds": 0.30,
            "mortgages": 0.20,
            "private_credit": 0.10,
        }
    )


def spia_saa() -> SAA:
    """SAA tuned for SPIA blocks (longer duration, more bonds)."""
    return SAA(
        weights={
            "govt_bonds": 0.50,
            "corp_bonds": 0.30,
            "mortgages": 0.10,
            "private_credit": 0.10,
        }
    )


def term_saa() -> SAA:
    """SAA tuned for Term blocks (shorter duration)."""
    return SAA(
        weights={
            "govt_bonds": 0.30,
            "corp_bonds": 0.30,
            "mortgages": 0.30,
            "private_credit": 0.10,
        }
    )


# ---------------------------------------------------------------------------
# Interest Rate Swap – Fixed for Floating
# ---------------------------------------------------------------------------


@dataclass
class InterestRateSwap:
    """Plain-vanilla fixed-for-floating interest rate swap.

    Used to adjust portfolio duration.  A **pay-fixed** position is
    economically equivalent to being short a fixed-rate bond and long
    a floating-rate note, giving *negative* duration contribution.
    A **receive-fixed** position is the opposite, adding duration.

    Parameters
    ----------
    notional : float
        Notional principal (never exchanged).
    fixed_rate : float
        Annual fixed rate as a decimal (e.g. 0.04 for 4 %).
    tenor : int
        Swap maturity in years.
    frequency : int
        Payment frequency per year (default 2 = semi-annual).
    pay_fixed : bool
        If True (default), this party pays fixed and receives floating.
        If False, this party receives fixed and pays floating.
    """

    notional: float
    fixed_rate: float
    tenor: int
    frequency: int = 2
    pay_fixed: bool = True

    @property
    def n_periods(self) -> int:
        return self.tenor * self.frequency

    def cashflows(self, floating_rates: list[float]) -> pl.DataFrame:
        """Net swap cash flows for each payment period.

        Parameters
        ----------
        floating_rates : list[float]
            Annualised floating rate that applies to each payment period.
            Must contain at least ``n_periods`` values.

        Columns: period, year, fixed_leg, floating_leg, net_cashflow.

        ``net_cashflow`` is from this party's perspective: positive means
        a net receipt, negative means a net payment.
        """
        n = self.n_periods
        fixed_pmt = self.notional * self.fixed_rate / self.frequency
        sign = -1.0 if self.pay_fixed else 1.0

        periods: list[int] = []
        years: list[float] = []
        fixed_legs: list[float] = []
        floating_legs: list[float] = []
        nets: list[float] = []

        for t in range(1, n + 1):
            float_pmt = self.notional * floating_rates[t - 1] / self.frequency
            net = sign * (fixed_pmt - float_pmt)

            periods.append(t)
            years.append(round(t / self.frequency, 6))
            fixed_legs.append(fixed_pmt)
            floating_legs.append(float_pmt)
            nets.append(net)

        return pl.DataFrame(
            {
                "period": periods,
                "year": years,
                "fixed_leg": fixed_legs,
                "floating_leg": floating_legs,
                "net_cashflow": nets,
            }
        )

    def present_value(self, floating_rates: list[float], discount_rate: float) -> float:
        """PV of net swap cash flows."""
        r = discount_rate / self.frequency
        cf = self.cashflows(floating_rates)
        pv = sum(
            ncf / (1 + r) ** t for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        if abs(pv) > self.notional:
            logger.warning(
                "Swap PV (%.2f) exceeds notional (%.2f); verify rates",
                pv,
                self.notional,
            )
        return pv

    def duration(self, floating_rates: list[float], discount_rate: float) -> float:
        """Macaulay duration in years."""
        r = discount_rate / self.frequency
        cf = self.cashflows(floating_rates)
        pv = self.present_value(floating_rates, discount_rate)
        weighted = sum(
            (t / self.frequency) * ncf / (1 + r) ** t
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        return weighted / pv

    def convexity(self, floating_rates: list[float], discount_rate: float) -> float:
        """Convexity (in years squared)."""
        r = discount_rate / self.frequency
        cf = self.cashflows(floating_rates)
        pv = self.present_value(floating_rates, discount_rate)
        conv = sum(
            t * (t + 1) * ncf / (1 + r) ** (t + 2)
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        return conv / (pv * self.frequency**2)

    def dv01(self, floating_rates: list[float], discount_rate: float) -> float:
        """Dollar value of one basis point (0.01 %) parallel rate shift.

        A parallel shift bumps *both* the floating rates and the discount
        rate by the same amount, which is how swap DV01 is conventionally
        measured.  Positive DV01 means the position gains value when
        rates fall.
        """
        bump = 0.0001
        floats_up = [r + bump for r in floating_rates]
        floats_down = [r - bump for r in floating_rates]
        pv_down = self.present_value(floats_down, discount_rate - bump)
        pv_up = self.present_value(floats_up, discount_rate + bump)
        return (pv_down - pv_up) / 2


# ---------------------------------------------------------------------------
# Block of Business
# ---------------------------------------------------------------------------

# Type aliases
AssetInstrument = "Bond | Mortgage | PrivateCredit"
LiabilityInstrument = "SPIA | WL | Term | FIA"


@dataclass
class Block:
    """A block of business with liabilities and matching assets.

    Represents a homogeneous group of insurance policies of a
    single liability type, along with the asset portfolio backing
    them according to a strategic asset allocation.

    Parameters
    ----------
    liability_type : str
        One of ``"SPIA"``, ``"WL"``, ``"Term"``, ``"FIA"``.
    saa : SAA
        Strategic asset allocation for this block.
    total_liability_amount : float
        Total starting liability amount (premium or face value).
    mortality_table : pl.DataFrame
        Mortality table (as from ``get_2012_iam_table()``).
    age_range : tuple[int, int]
        ``(min_age, max_age)`` for random policy generation.
    discount_rate : float
        Flat annual discount rate for PV calculations.
    n_policies : int
        Number of individual policies to generate.
    gender_split : float
        Proportion male (0.0 = all female, 1.0 = all male).
    seed : int
        Random seed for reproducibility.
    index_rates : list[float]
        Annual index rates for FIA crediting (required if
        liability_type is ``"FIA"``).
    premium : float, optional
        Total investable amount (premium collected).  If ``None``
        (default), it is computed automatically as
        ``PV(expected benefits) * (1 + profit_margin)`` when
        assets are generated.
    profit_margin : float
        Markup over the actuarial PV of benefits used when
        computing premium automatically (default 0.05 = 5 %).
    """

    liability_type: str
    saa: SAA
    total_liability_amount: float
    mortality_table: pl.DataFrame
    age_range: tuple[int, int]
    discount_rate: float
    n_policies: int = 500
    gender_split: float = 0.5
    seed: int = 42
    index_rates: list[float] = field(default_factory=list)
    premium: float | None = None
    profit_margin: float = 0.05

    # Internal state (populated by generate methods)
    _policies: list = field(default_factory=list, init=False, repr=False)
    _assets: list = field(default_factory=list, init=False, repr=False)

    _VALID_TYPES = {"SPIA", "WL", "Term", "FIA"}

    def __post_init__(self) -> None:
        if self.liability_type not in self._VALID_TYPES:
            raise ValueError(
                f"liability_type must be one of {self._VALID_TYPES}, got '{self.liability_type}'"
            )
        if not 0.0 <= self.gender_split <= 1.0:
            raise ValueError(f"gender_split must be in [0, 1], got {self.gender_split}")

    def calculate_premium(self) -> float:
        """Compute the total investable premium from liability PVs.

        Uses the equivalence principle:
        ``premium = PV(expected benefits) * (1 + profit_margin)``.

        If policies have not been generated yet, generates them first.
        The result is stored in ``self.premium`` and returned.
        """
        from alm.liability import FIA, SPIA

        if not self._policies:
            self.generate_policies()

        pv_benefits = 0.0
        for policy in self._policies:
            if isinstance(policy, SPIA):
                cf = policy.cashflows()
                r = self.discount_rate / policy.frequency
                pv_benefits += sum(
                    ep / (1 + r) ** t
                    for t, ep in zip(cf["period"], cf["expected_payout"], strict=True)
                )
            elif isinstance(policy, FIA):
                cf = policy.cashflows(self.index_rates)
                pv_benefits += sum(
                    ncf / (1 + self.discount_rate) ** yr
                    for yr, ncf in zip(cf["year"], cf["net_cashflow"], strict=True)
                )
            else:
                # WL, Term — discount expected benefit outflows only
                cf = policy.cashflows()
                r = self.discount_rate / policy.frequency
                pv_benefits += sum(
                    eb / (1 + r) ** t
                    for t, eb in zip(cf["period"], cf["expected_benefit"], strict=True)
                )

        self.premium = pv_benefits * (1 + self.profit_margin)
        logger.info(
            "Calculated premium: $%s  (PV benefits $%s × %.1f%%)",
            f"{self.premium:,.0f}",
            f"{pv_benefits:,.0f}",
            (1 + self.profit_margin) * 100,
        )
        return self.premium

    def generate_policies(self) -> list:
        """Create N individual liability policies with randomized
        ages and genders.

        Each policy gets a pro-rata share of the total liability
        amount.  Uses stdlib ``random.Random`` for reproducibility.
        """
        from alm.liability import FIA, SPIA, WL, Term, qx_from_table

        rng = random.Random(self.seed)
        min_age, max_age = self.age_range
        per_policy = self.total_liability_amount / self.n_policies

        policies: list = []
        for _ in range(self.n_policies):
            age = rng.randint(min_age, max_age)
            sex = rng.choices(
                ["male", "female"],
                weights=[self.gender_split, 1.0 - self.gender_split],
            )[0]
            qx = qx_from_table(self.mortality_table, age, sex)

            if self.liability_type == "SPIA":
                policy = SPIA(
                    premium=per_policy,
                    annual_payout=per_policy * 0.06,
                    qx=qx,
                    age=age,
                )
            elif self.liability_type == "WL":
                policy = WL(
                    face_value=per_policy,
                    annual_premium=per_policy * 0.015,
                    qx=qx,
                    age=age,
                )
            elif self.liability_type == "Term":
                policy = Term(
                    face_value=per_policy,
                    annual_premium=per_policy * 0.005,
                    term=20,
                    qx=qx,
                    age=age,
                )
            elif self.liability_type == "FIA":
                policy = FIA(
                    premium=per_policy,
                    term=10,
                    qx=qx,
                    age=age,
                )
            policies.append(policy)

        self._policies = policies
        return policies

    def generate_assets(self) -> list:
        """Create asset positions according to SAA weights.

        Bond maturities are chosen to roughly match the liability
        block's general duration profile.  The total amount allocated
        is based on ``self.premium`` (the investable amount).  If
        premium has not been set or calculated, it is computed
        automatically via :meth:`calculate_premium`.

        Credit spreads are looked up from ``assumptions/credit_spreads.csv``
        based on each bond's rating and maturity.  Allocations within each
        asset class are split across credit ratings using the module-level
        ``GOVT_RATING_DIST``, ``CORP_RATING_DIST``, and ``PC_RATING_DIST``
        dictionaries.
        """
        from alm.asset import Bond, Mortgage, PrivateCredit
        from alm.read import get_spread

        if self.premium is None:
            self.calculate_premium()

        alloc = self.saa.allocation(self.premium)
        duration_profiles: dict[str, list[int]] = {
            "SPIA": [5, 10, 20, 30],
            "WL": [5, 10, 20, 30],
            "Term": [3, 5, 10],
            "FIA": [3, 5, 7, 10],
        }
        maturities = duration_profiles[self.liability_type]
        assets: list = []

        # Government bonds — split by rating and maturity
        if alloc.get("govt_bonds", 0) > 0:
            amt = alloc["govt_bonds"]
            for rating, weight in GOVT_RATING_DIST.items():
                for mat in maturities:
                    spread = get_spread(rating, mat)
                    assets.append(
                        Bond(
                            face_value=amt * weight / len(maturities),
                            coupon_rate=self.discount_rate + spread,
                            maturity=mat,
                            rating=rating,
                            credit_spread=spread,
                        )
                    )

        # Corporate bonds — split by rating and maturity
        if alloc.get("corp_bonds", 0) > 0:
            amt = alloc["corp_bonds"]
            for rating, weight in CORP_RATING_DIST.items():
                for mat in maturities:
                    spread = get_spread(rating, mat)
                    assets.append(
                        Bond(
                            face_value=amt * weight / len(maturities),
                            coupon_rate=self.discount_rate + spread,
                            maturity=mat,
                            rating=rating,
                            credit_spread=spread,
                        )
                    )

        # Mortgages — use average A-rated spread as mortgage spread
        if alloc.get("mortgages", 0) > 0:
            amt = alloc["mortgages"]
            assets.append(
                Mortgage(
                    principal=amt * 0.5,
                    annual_rate=self.discount_rate + get_spread("A", 15),
                    term=15,
                )
            )
            assets.append(
                Mortgage(
                    principal=amt * 0.5,
                    annual_rate=self.discount_rate + get_spread("A", 30),
                    term=30,
                )
            )

        # Private credit — split by rating
        if alloc.get("private_credit", 0) > 0:
            amt = alloc["private_credit"]
            pc_mats = [3, 5]
            for rating, weight in PC_RATING_DIST.items():
                for mat in pc_mats:
                    spread = get_spread(rating, mat)
                    assets.append(
                        PrivateCredit(
                            face_value=amt * weight / len(pc_mats),
                            maturity=mat,
                            risk_free_rate=self.discount_rate,
                            credit_spread=spread,
                            illiquidity_spread=0.020,
                            other_spread=0.005,
                            rating=rating,
                        )
                    )

        self._assets = assets
        return assets

    def liability_cashflows(self) -> pl.DataFrame:
        """Aggregate cashflows across all individual policies.

        Returns
        -------
        pl.DataFrame
            Columns: ``year`` (Int32), ``cashflow`` (Float64).
        """
        from alm.liability import FIA, SPIA

        if not self._policies:
            self.generate_policies()

        all_rows: list[pl.DataFrame] = []
        for policy in self._policies:
            if isinstance(policy, FIA):
                cf = policy.cashflows(self.index_rates)
                cf = cf.select(
                    "year",
                    pl.col("net_cashflow").alias("cashflow"),
                )
            elif isinstance(policy, SPIA):
                cf = policy.cashflows()
                cf = cf.select(
                    "year",
                    pl.col("expected_payout").alias("cashflow"),
                )
            else:
                # WL, Term — expected benefit outflows only
                cf = policy.cashflows()
                cf = cf.select(
                    "year",
                    pl.col("expected_benefit").alias("cashflow"),
                )
            # Annualise: ceil year to integer
            cf = (
                cf.with_columns(pl.col("year").cast(pl.Float64).ceil().cast(pl.Int32))
                .group_by("year")
                .agg(pl.col("cashflow").sum())
            )
            all_rows.append(cf)

        return pl.concat(all_rows).group_by("year").agg(pl.col("cashflow").sum()).sort("year")

    def asset_cashflows(self) -> pl.DataFrame:
        """Aggregate cashflows across all asset positions.

        Returns
        -------
        pl.DataFrame
            Columns: ``year`` (Int32), ``cashflow`` (Float64).
        """
        from alm.asset import Bond, PrivateCredit

        if not self._assets:
            self.generate_assets()

        all_rows: list[pl.DataFrame] = []
        for inst in self._assets:
            cf = inst.cashflows()
            freq = inst.frequency

            if isinstance(inst, (Bond, PrivateCredit)):
                cf = cf.with_columns((pl.col("period") / freq).alias("year")).select(
                    "year", pl.col("total").alias("cashflow")
                )
            else:
                # Mortgage
                cf = cf.with_columns((pl.col("period") / freq).alias("year")).select(
                    "year", pl.col("payment").alias("cashflow")
                )

            cf = (
                cf.with_columns(pl.col("year").cast(pl.Float64).ceil().cast(pl.Int32))
                .group_by("year")
                .agg(pl.col("cashflow").sum())
            )
            all_rows.append(cf)

        return pl.concat(all_rows).group_by("year").agg(pl.col("cashflow").sum()).sort("year")

    def plot_cashflows(self):
        """Plot asset vs liability cashflows.

        Returns a Plotly Figure with grouped bars.
        """
        from alm import plot

        liab_cf = self.liability_cashflows()
        asset_cf = self.asset_cashflows()

        combined = (
            asset_cf.rename({"cashflow": "assets"})
            .join(
                liab_cf.rename({"cashflow": "liabilities"}),
                on="year",
                how="full",
                coalesce=True,
            )
            .fill_null(0.0)
            .sort("year")
        )

        return plot.bar_chart(
            combined,
            x="year",
            y=["assets", "liabilities"],
            title=(f"{self.liability_type} Block — Assets vs Liabilities"),
            xlab="Year",
            ylab="Annual Cashflow",
            yformat="$",
            barmode="group",
        )

    def reinvest(self, year: int) -> list:
        """Reinvest proceeds from matured bonds at the given year
        according to SAA weights.

        Parameters
        ----------
        year : int
            The year at which reinvestment occurs.

        Returns
        -------
        list
            New asset instruments created from reinvestment.
        """
        from alm.asset import Bond, Mortgage, PrivateCredit
        from alm.read import get_spread

        matured_proceeds = 0.0
        remaining: list = []

        for inst in self._assets:
            if isinstance(inst, (Bond, PrivateCredit)):
                if inst.maturity < year:
                    matured_proceeds += inst.face_value
                else:
                    remaining.append(inst)
            else:
                remaining.append(inst)

        if matured_proceeds <= 0:
            return []

        alloc = self.saa.allocation(matured_proceeds)
        new_assets: list = []

        if alloc.get("govt_bonds", 0) > 0:
            amt = alloc["govt_bonds"]
            for rating, weight in GOVT_RATING_DIST.items():
                spread = get_spread(rating, 5)
                new_assets.append(
                    Bond(
                        face_value=amt * weight,
                        coupon_rate=self.discount_rate + spread,
                        maturity=5,
                        rating=rating,
                        credit_spread=spread,
                    )
                )

        if alloc.get("corp_bonds", 0) > 0:
            amt = alloc["corp_bonds"]
            for rating, weight in CORP_RATING_DIST.items():
                spread = get_spread(rating, 5)
                new_assets.append(
                    Bond(
                        face_value=amt * weight,
                        coupon_rate=self.discount_rate + spread,
                        maturity=5,
                        rating=rating,
                        credit_spread=spread,
                    )
                )

        if alloc.get("mortgages", 0) > 0:
            new_assets.append(
                Mortgage(
                    principal=alloc["mortgages"],
                    annual_rate=self.discount_rate + get_spread("A", 15),
                    term=15,
                )
            )

        if alloc.get("private_credit", 0) > 0:
            amt = alloc["private_credit"]
            for rating, weight in PC_RATING_DIST.items():
                spread = get_spread(rating, 5)
                new_assets.append(
                    PrivateCredit(
                        face_value=amt * weight,
                        maturity=5,
                        risk_free_rate=self.discount_rate,
                        credit_spread=spread,
                        illiquidity_spread=0.020,
                        other_spread=0.005,
                        rating=rating,
                    )
                )

        self._assets = remaining + new_assets
        return new_assets
