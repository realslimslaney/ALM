"""Insurance liability models for ALM."""

import logging
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


def qx_from_table(table: pl.DataFrame, age: int, sex: str | None = None) -> list[float]:
    """Extract qx values from a mortality table starting at a given age.

    Parameters
    ----------
    table : pl.DataFrame
        Mortality table with columns ``age`` (Int64) and ``qx`` (Float64),
        as returned by :func:`alm.read.read_mortality_table` or
        :func:`alm.read.get_2012_iam_table`.
    age : int
        Issue age (inclusive).  Returns qx from this age to the end of
        the table.
    sex : str, optional
        ``"male"`` or ``"female"``.  Required when *table* contains
        both sexes (i.e. from :func:`~alm.read.get_2012_iam_table`).

    Returns
    -------
    list[float]
        ``qx[0]`` corresponds to age *age*, ``qx[1]`` to *age + 1*, etc.
    """
    subset = table
    if sex is not None:
        subset = subset.filter(pl.col("sex") == sex.lower())
    subset = subset.filter(pl.col("age") >= age).sort("age")
    if subset.is_empty():
        raise ValueError(f"No rows in mortality table for age >= {age}")
    return subset["qx"].to_list()


def _validate_qx(qx: list[float]) -> None:
    """Warn if any qx values look unreasonable."""
    for i, q in enumerate(qx):
        if q < 0 or q > 1:
            logger.warning("qx[%d] = %.4f is outside [0, 1]", i, q)
        elif q > 0.5:
            logger.warning("qx[%d] = %.4f is unusually high (>50%%)", i, q)


def _survival_prob(qx: list[float], t: float) -> float:
    """Probability of surviving from time 0 to *t* years (UDD within each year).

    Parameters
    ----------
    qx : list[float]
        Annual mortality rates where ``qx[k]`` is the probability of death
        in year *k* (from time *k* to *k + 1*).
    t : float
        Elapsed time in years.
    """
    year = int(t)
    frac = t - year

    sp = 1.0
    for k in range(min(year, len(qx))):
        sp *= 1 - qx[k]

    if frac > 0 and year < len(qx):
        sp *= 1 - frac * qx[year]

    return sp


# ---------------------------------------------------------------------------
# SPIA – Single Premium Immediate Annuity
# ---------------------------------------------------------------------------


@dataclass
class SPIA:
    """Single Premium Immediate Annuity.

    Policyholder pays a lump-sum premium and receives periodic income
    for life, with an optional certain-period guarantee.

    Parameters
    ----------
    premium : float
        Single premium paid at issue.
    annual_payout : float
        Total annual payout to the annuitant.
    qx : list[float]
        Annual mortality rates from the annuitant's current age.
        Length determines the modelling horizon.  Use
        :func:`qx_from_table` to build from a mortality table.
    frequency : int
        Payouts per year (default 12 = monthly).
    certain_period : int
        Guaranteed payment period in years (default 0 = life only).
    age : int, optional
        Issue age — stored for reference, does not affect calculations.
    """

    premium: float
    annual_payout: float
    qx: list[float]
    frequency: int = 12
    certain_period: int = 0
    age: int | None = None

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

    def __repr__(self) -> str:
        qx_summary = f"[{self.qx[0]:.4f}, ..., {self.qx[-1]:.4f}] ({len(self.qx)} rates)"
        return (
            f"SPIA(premium={self.premium:,.0f}, annual_payout={self.annual_payout:,.0f}, "
            f"qx={qx_summary}, freq={self.frequency}, certain={self.certain_period}, "
            f"age={self.age})"
        )

    def cashflows(self) -> pl.DataFrame:
        """Expected liability cash flows (insurer outflows).

        Columns: period, year, payout, survival_prob, expected_payout.
        """
        pmt = self.annual_payout / self.frequency
        n_periods = len(self.qx) * self.frequency

        periods, years_col = [], []
        payouts, surv_probs, expected = [], [], []

        for t in range(1, n_periods + 1):
            yr = t / self.frequency
            sp = _survival_prob(self.qx, yr)
            exp = pmt if yr <= self.certain_period else pmt * sp

            periods.append(t)
            years_col.append(round(yr, 6))
            payouts.append(pmt)
            surv_probs.append(sp)
            expected.append(exp)

        return pl.DataFrame(
            {
                "period": periods,
                "year": years_col,
                "payout": payouts,
                "survival_prob": surv_probs,
                "expected_payout": expected,
            }
        )

    def present_value(self, discount_rate: float) -> float:
        """PV of expected payouts."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        return sum(
            ep / (1 + r) ** t for t, ep in zip(cf["period"], cf["expected_payout"], strict=True)
        )

    def duration(self, discount_rate: float) -> float:
        """Macaulay duration in years."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)
        weighted = sum(
            (t / self.frequency) * ep / (1 + r) ** t
            for t, ep in zip(cf["period"], cf["expected_payout"], strict=True)
        )
        return weighted / pv

    def convexity(self, discount_rate: float) -> float:
        """Convexity (in years squared)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)
        conv = sum(
            t * (t + 1) * ep / (1 + r) ** (t + 2)
            for t, ep in zip(cf["period"], cf["expected_payout"], strict=True)
        )
        return conv / (pv * self.frequency**2)

    @classmethod
    def from_payout(
        cls,
        annual_payout: float,
        qx: list[float],
        discount_rate: float,
        frequency: int = 12,
        certain_period: int = 0,
        age: int | None = None,
    ) -> "SPIA":
        """Create a SPIA with actuarially fair single premium.

        The fair premium equals the present value of expected payouts
        at the given discount rate.
        """
        temp = cls(
            premium=0.0,
            annual_payout=annual_payout,
            qx=qx,
            frequency=frequency,
            certain_period=certain_period,
            age=age,
        )
        return cls(
            premium=temp.present_value(discount_rate),
            annual_payout=annual_payout,
            qx=qx,
            frequency=frequency,
            certain_period=certain_period,
            age=age,
        )


# ---------------------------------------------------------------------------
# WL – Whole Life Insurance
# ---------------------------------------------------------------------------


@dataclass
class WL:
    """Whole Life Insurance.

    Level-premium whole life policy paying a death benefit
    whenever the insured dies.

    Parameters
    ----------
    face_value : float
        Death benefit amount.
    annual_premium : float
        Level annual premium.
    qx : list[float]
        Annual mortality rates from the insured's current age.
        Use :func:`qx_from_table` to build from a mortality table.
    frequency : int
        Premium payment frequency per year (default 12 = monthly).
    age : int, optional
        Issue age — stored for reference, does not affect calculations.
    """

    face_value: float
    annual_premium: float
    qx: list[float]
    frequency: int = 12
    age: int | None = None

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

    def __repr__(self) -> str:
        qx_summary = f"[{self.qx[0]:.4f}, ..., {self.qx[-1]:.4f}] ({len(self.qx)} rates)"
        return (
            f"WL(face={self.face_value:,.0f}, premium={self.annual_premium:,.0f}, "
            f"qx={qx_summary}, freq={self.frequency}, age={self.age})"
        )

    def cashflows(self) -> pl.DataFrame:
        """Expected liability cash flows.

        Columns: period, year, survival_prob, expected_premium,
                 expected_benefit, net_cashflow.

        ``net_cashflow = expected_benefit - expected_premium``
        (positive = net outflow for the insurer).
        """
        pmt = self.annual_premium / self.frequency
        n_periods = len(self.qx) * self.frequency

        periods, years_col = [], []
        surv_probs, exp_premiums, exp_benefits, nets = [], [], [], []

        for t in range(1, n_periods + 1):
            yr_start = (t - 1) / self.frequency
            yr_end = t / self.frequency
            sp_start = _survival_prob(self.qx, yr_start)
            sp_end = _survival_prob(self.qx, yr_end)
            death_prob = sp_start - sp_end

            exp_prem = pmt * sp_start
            exp_ben = self.face_value * death_prob

            periods.append(t)
            years_col.append(round(yr_end, 6))
            surv_probs.append(sp_end)
            exp_premiums.append(exp_prem)
            exp_benefits.append(exp_ben)
            nets.append(exp_ben - exp_prem)

        return pl.DataFrame(
            {
                "period": periods,
                "year": years_col,
                "survival_prob": surv_probs,
                "expected_premium": exp_premiums,
                "expected_benefit": exp_benefits,
                "net_cashflow": nets,
            }
        )

    def present_value(self, discount_rate: float) -> float:
        """PV of net liability cash flows (benefits minus premiums)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        return sum(
            ncf / (1 + r) ** t for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )

    def duration(self, discount_rate: float) -> float:
        """Macaulay duration of net liability in years."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)
        weighted = sum(
            (t / self.frequency) * ncf / (1 + r) ** t
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        return weighted / pv

    def convexity(self, discount_rate: float) -> float:
        """Convexity of net liability (in years squared)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)
        conv = sum(
            t * (t + 1) * ncf / (1 + r) ** (t + 2)
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        return conv / (pv * self.frequency**2)

    @classmethod
    def from_face(
        cls,
        face_value: float,
        qx: list[float],
        discount_rate: float,
        frequency: int = 12,
        age: int | None = None,
    ) -> "WL":
        """Create a WL with net level premium via the equivalence principle.

        Solves for the annual premium P such that PV(premiums) = PV(benefits).
        """
        r = discount_rate / frequency
        n_periods = len(qx) * frequency

        pv_benefits = 0.0
        pv_annuity = 0.0

        for t in range(1, n_periods + 1):
            yr_start = (t - 1) / frequency
            yr_end = t / frequency
            sp_start = _survival_prob(qx, yr_start)
            sp_end = _survival_prob(qx, yr_end)
            death_prob = sp_start - sp_end
            v_t = (1 + r) ** (-t)

            pv_benefits += face_value * death_prob * v_t
            pv_annuity += (sp_start / frequency) * v_t

        fair_annual_premium = pv_benefits / pv_annuity
        return cls(
            face_value=face_value,
            annual_premium=fair_annual_premium,
            qx=qx,
            frequency=frequency,
            age=age,
        )


# ---------------------------------------------------------------------------
# Term – Term Life Insurance
# ---------------------------------------------------------------------------


@dataclass
class Term:
    """Term Life Insurance.

    Level-premium term policy paying a death benefit only if the
    insured dies within the policy term.

    Parameters
    ----------
    face_value : float
        Death benefit amount.
    annual_premium : float
        Level annual premium.
    term : int
        Policy term in years.
    qx : list[float]
        Annual mortality rates from the insured's current age.
        Must have at least *term* values.  Use :func:`qx_from_table`
        to build from a mortality table.
    frequency : int
        Premium payment frequency per year (default 12 = monthly).
    age : int, optional
        Issue age — stored for reference, does not affect calculations.
    """

    face_value: float
    annual_premium: float
    term: int
    qx: list[float]
    frequency: int = 12
    age: int | None = None

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

    def __repr__(self) -> str:
        qx_summary = f"[{self.qx[0]:.4f}, ..., {self.qx[-1]:.4f}] ({len(self.qx)} rates)"
        return (
            f"Term(face={self.face_value:,.0f}, premium={self.annual_premium:,.0f}, "
            f"term={self.term}, qx={qx_summary}, freq={self.frequency}, age={self.age})"
        )

    def cashflows(self) -> pl.DataFrame:
        """Expected liability cash flows over the policy term.

        Same structure as :meth:`WL.cashflows`.
        """
        pmt = self.annual_premium / self.frequency
        n_periods = self.term * self.frequency

        periods, years_col = [], []
        surv_probs, exp_premiums, exp_benefits, nets = [], [], [], []

        for t in range(1, n_periods + 1):
            yr_start = (t - 1) / self.frequency
            yr_end = t / self.frequency
            sp_start = _survival_prob(self.qx, yr_start)
            sp_end = _survival_prob(self.qx, yr_end)
            death_prob = sp_start - sp_end

            exp_prem = pmt * sp_start
            exp_ben = self.face_value * death_prob

            periods.append(t)
            years_col.append(round(yr_end, 6))
            surv_probs.append(sp_end)
            exp_premiums.append(exp_prem)
            exp_benefits.append(exp_ben)
            nets.append(exp_ben - exp_prem)

        return pl.DataFrame(
            {
                "period": periods,
                "year": years_col,
                "survival_prob": surv_probs,
                "expected_premium": exp_premiums,
                "expected_benefit": exp_benefits,
                "net_cashflow": nets,
            }
        )

    def present_value(self, discount_rate: float) -> float:
        """PV of net liability cash flows (benefits minus premiums)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        return sum(
            ncf / (1 + r) ** t for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )

    def duration(self, discount_rate: float) -> float:
        """Macaulay duration of net liability in years."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)
        weighted = sum(
            (t / self.frequency) * ncf / (1 + r) ** t
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        return weighted / pv

    def convexity(self, discount_rate: float) -> float:
        """Convexity of net liability (in years squared)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)
        conv = sum(
            t * (t + 1) * ncf / (1 + r) ** (t + 2)
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
        )
        return conv / (pv * self.frequency**2)


# ---------------------------------------------------------------------------
# FIA – Fixed Indexed Annuity
# ---------------------------------------------------------------------------


@dataclass
class FIA:
    """Fixed Indexed Annuity.

    Single-premium deferred annuity whose credited rate tracks an
    external reference rate (e.g. a FRED Treasury series), subject
    to an annual floor and cap.

    Parameters
    ----------
    premium : float
        Single premium paid at issue.
    term : int
        Accumulation period in years.
    qx : list[float]
        Annual mortality rates from the annuitant's current age.
        Must have at least *term* values.  Use :func:`qx_from_table`
        to build from a mortality table.
    floor : float
        Minimum annual credited rate (default 0.0 = 0 %).
    cap : float
        Maximum annual credited rate (default 0.06 = 6 %).
    participation_rate : float
        Fraction of the index return credited to the account (default 1.0).
    age : int, optional
        Issue age — stored for reference, does not affect calculations.
    """

    premium: float
    term: int
    qx: list[float]
    floor: float = 0.0
    cap: float = 0.06
    participation_rate: float = 1.0
    age: int | None = None

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

    def __repr__(self) -> str:
        qx_summary = f"[{self.qx[0]:.4f}, ..., {self.qx[-1]:.4f}] ({len(self.qx)} rates)"
        return (
            f"FIA(premium={self.premium:,.0f}, term={self.term}, "
            f"qx={qx_summary}, floor={self.floor:.1%}, cap={self.cap:.1%}, "
            f"age={self.age})"
        )

    def credited_rate(self, index_rate: float) -> float:
        """Apply participation rate, floor, and cap to a single index rate."""
        return max(self.floor, min(self.cap, index_rate * self.participation_rate))

    def _build_account_values(self, index_rates: list[float]) -> list[float]:
        """Return account values ``[AV_0, AV_1, ..., AV_term]``."""
        av = float(self.premium)
        avs = [av]
        for rate in index_rates[: self.term]:
            av *= 1 + self.credited_rate(rate)
            avs.append(av)
        return avs

    def account_values(self, index_rates: list[float]) -> pl.DataFrame:
        """Year-by-year account value accumulation.

        Parameters
        ----------
        index_rates : list[float]
            Annual reference rates for each year of the term.

        Columns: year, index_rate, credited_rate, account_value.
        """
        avs = self._build_account_values(index_rates)

        years_col = [0]
        ir_col = [0.0]
        cr_col = [0.0]
        av_col = [avs[0]]

        for yr, rate in enumerate(index_rates[: self.term], start=1):
            years_col.append(yr)
            ir_col.append(rate)
            cr_col.append(self.credited_rate(rate))
            av_col.append(avs[yr])

        return pl.DataFrame(
            {
                "year": years_col,
                "index_rate": ir_col,
                "credited_rate": cr_col,
                "account_value": av_col,
            }
        )

    def cashflows(self, index_rates: list[float]) -> pl.DataFrame:
        """Expected liability cash flows (annual).

        Parameters
        ----------
        index_rates : list[float]
            Annual reference rates for each year of the term.

        Columns: year, account_value, survival_prob, death_prob,
                 expected_death_benefit, expected_maturity_benefit,
                 net_cashflow.
        """
        avs = self._build_account_values(index_rates)

        years_col, av_col = [], []
        surv_probs, death_probs = [], []
        exp_death, exp_maturity, nets = [], [], []

        for yr in range(1, self.term + 1):
            av = avs[yr]
            sp_start = _survival_prob(self.qx, yr - 1)
            sp_end = _survival_prob(self.qx, yr)
            dp = sp_start - sp_end

            ed = av * dp
            em = av * sp_end if yr == self.term else 0.0

            years_col.append(yr)
            av_col.append(av)
            surv_probs.append(sp_end)
            death_probs.append(dp)
            exp_death.append(ed)
            exp_maturity.append(em)
            nets.append(ed + em)

        return pl.DataFrame(
            {
                "year": years_col,
                "account_value": av_col,
                "survival_prob": surv_probs,
                "death_prob": death_probs,
                "expected_death_benefit": exp_death,
                "expected_maturity_benefit": exp_maturity,
                "net_cashflow": nets,
            }
        )

    def present_value(self, index_rates: list[float], discount_rate: float) -> float:
        """PV of expected liability cash flows."""
        cf = self.cashflows(index_rates)
        return sum(
            ncf / (1 + discount_rate) ** yr
            for yr, ncf in zip(cf["year"], cf["net_cashflow"], strict=True)
        )

    def duration(self, index_rates: list[float], discount_rate: float) -> float:
        """Macaulay duration in years."""
        cf = self.cashflows(index_rates)
        pv = self.present_value(index_rates, discount_rate)
        weighted = sum(
            yr * ncf / (1 + discount_rate) ** yr
            for yr, ncf in zip(cf["year"], cf["net_cashflow"], strict=True)
        )
        return weighted / pv

    def convexity(self, index_rates: list[float], discount_rate: float) -> float:
        """Convexity (in years squared)."""
        cf = self.cashflows(index_rates)
        pv = self.present_value(index_rates, discount_rate)
        conv = sum(
            yr * (yr + 1) * ncf / (1 + discount_rate) ** (yr + 2)
            for yr, ncf in zip(cf["year"], cf["net_cashflow"], strict=True)
        )
        return conv / pv
