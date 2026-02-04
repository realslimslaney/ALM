"""Insurance liability models for ALM."""

import logging
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


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
        Length determines the modelling horizon.
    frequency : int
        Payouts per year (default 12 = monthly).
    certain_period : int
        Guaranteed payment period in years (default 0 = life only).
    """

    premium: float
    annual_payout: float
    qx: list[float]
    frequency: int = 12
    certain_period: int = 0

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

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
            ep / (1 + r) ** t
            for t, ep in zip(cf["period"], cf["expected_payout"], strict=True)
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
    frequency : int
        Premium payment frequency per year (default 12 = monthly).
    """

    face_value: float
    annual_premium: float
    qx: list[float]
    frequency: int = 12

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

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
            ncf / (1 + r) ** t
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
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
        Must have at least *term* values.
    frequency : int
        Premium payment frequency per year (default 12 = monthly).
    """

    face_value: float
    annual_premium: float
    term: int
    qx: list[float]
    frequency: int = 12

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

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
            ncf / (1 + r) ** t
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
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
        Must have at least *term* values.
    floor : float
        Minimum annual credited rate (default 0.0 = 0 %).
    cap : float
        Maximum annual credited rate (default 0.06 = 6 %).
    participation_rate : float
        Fraction of the index return credited to the account (default 1.0).
    """

    premium: float
    term: int
    qx: list[float]
    floor: float = 0.0
    cap: float = 0.06
    participation_rate: float = 1.0

    def __post_init__(self) -> None:
        _validate_qx(self.qx)

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
