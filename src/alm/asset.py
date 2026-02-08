"""Fixed-income asset models."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


@dataclass
class Bond:
    """A plain-vanilla fixed-coupon bullet bond.

    Parameters
    ----------
    face_value : float
        Par / face value of the bond.
    coupon_rate : float
        Annual coupon rate expressed as a decimal (e.g. 0.05 for 5 %).
    maturity : int
        Years to maturity.
    frequency : int
        Coupon payments per year (default 2 = semi-annual).
    rating : str or None
        Optional credit rating label (e.g. "AA", "BBB").
    credit_spread : float
        Credit spread component of the coupon rate, for reporting.
    """

    face_value: float
    coupon_rate: float
    maturity: int
    frequency: int = 2
    rating: str | None = None
    credit_spread: float = 0.0

    @property
    def n_periods(self) -> int:
        return self.maturity * self.frequency

    @property
    def coupon(self) -> float:
        """Per-period coupon payment."""
        return self.face_value * self.coupon_rate / self.frequency

    def cashflows(self) -> pl.DataFrame:
        """Return the cash-flow schedule.

        Columns: period, coupon, principal, total.
        """
        n = self.n_periods
        c = self.coupon

        periods = list(range(1, n + 1))
        coupons = [c] * n
        principals = [0.0] * (n - 1) + [self.face_value]
        totals = [c + p for c, p in zip(coupons, principals, strict=True)]

        return pl.DataFrame(
            {
                "period": periods,
                "coupon": coupons,
                "principal": principals,
                "total": totals,
            }
        )

    def present_value(self, discount_rate: float) -> float:
        """Present value at a flat annual discount rate."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = sum(total / (1 + r) ** t for t, total in zip(cf["period"], cf["total"], strict=True))
        if pv < 0:
            logger.warning("Bond PV is negative (%.2f); check discount rate", pv)
        return pv

    def duration(self, discount_rate: float) -> float:
        """Macaulay duration in years."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)

        weighted = sum(
            (t / self.frequency) * total / (1 + r) ** t
            for t, total in zip(cf["period"], cf["total"], strict=True)
        )
        dur = weighted / pv
        if dur < 0 or dur > self.maturity:
            logger.warning("Bond duration %.2f outside expected range [0, %d]", dur, self.maturity)
        return dur

    def convexity(self, discount_rate: float) -> float:
        """Convexity (in years squared)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)

        conv = sum(
            t * (t + 1) * total / (1 + r) ** (t + 2)
            for t, total in zip(cf["period"], cf["total"], strict=True)
        )
        return conv / (pv * self.frequency**2)


@dataclass
class Mortgage:
    """A plain-vanilla fixed-rate fully-amortizing mortgage.

    Parameters
    ----------
    principal : float
        Original loan amount.
    annual_rate : float
        Fixed annual interest rate as a decimal (e.g. 0.06 for 6 %).
    term : int
        Loan term in years.
    frequency : int
        Payments per year (default 12 = monthly).
    """

    principal: float
    annual_rate: float
    term: int
    frequency: int = 12

    @property
    def periodic_rate(self) -> float:
        return self.annual_rate / self.frequency

    @property
    def n_periods(self) -> int:
        return self.term * self.frequency

    @property
    def payment(self) -> float:
        """Level periodic payment amount."""
        r = self.periodic_rate
        n = self.n_periods
        return self.principal * r * (1 + r) ** n / ((1 + r) ** n - 1)

    def balance_at(self, period: int) -> float:
        """Outstanding balance after *period* payments (closed-form)."""
        r = self.periodic_rate
        n = self.n_periods
        return self.principal * ((1 + r) ** n - (1 + r) ** period) / ((1 + r) ** n - 1)

    def cashflows(self) -> pl.DataFrame:
        """Return the full amortisation schedule.

        Columns: period, payment, interest, principal, balance.
        """
        r = self.periodic_rate
        pmt = self.payment
        balance = self.principal

        periods, payments, interests, principals, balances = [], [], [], [], []

        for t in range(1, self.n_periods + 1):
            interest = balance * r
            princ = pmt - interest
            balance -= princ

            periods.append(t)
            payments.append(pmt)
            interests.append(interest)
            principals.append(princ)
            balances.append(max(balance, 0.0))

        return pl.DataFrame(
            {
                "period": periods,
                "payment": payments,
                "interest": interests,
                "principal": principals,
                "balance": balances,
            }
        )

    def present_value(self, discount_rate: float) -> float:
        """Present value at a flat annual discount rate."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = sum(pmt / (1 + r) ** t for t, pmt in zip(cf["period"], cf["payment"], strict=True))
        if pv < 0:
            logger.warning("Mortgage PV is negative (%.2f); check discount rate", pv)
        return pv

    def duration(self, discount_rate: float) -> float:
        """Macaulay duration in years."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)

        weighted = sum(
            (t / self.frequency) * pmt / (1 + r) ** t
            for t, pmt in zip(cf["period"], cf["payment"], strict=True)
        )
        dur = weighted / pv
        if dur < 0 or dur > self.term:
            logger.warning(
                "Mortgage duration %.2f outside expected range [0, %d]",
                dur,
                self.term,
            )
        return dur

    def convexity(self, discount_rate: float) -> float:
        """Convexity (in years squared)."""
        r = discount_rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(discount_rate)

        conv = sum(
            t * (t + 1) * pmt / (1 + r) ** (t + 2)
            for t, pmt in zip(cf["period"], cf["payment"], strict=True)
        )
        return conv / (pv * self.frequency**2)


@dataclass
class PrivateCredit:
    """Private credit instrument with explicit yield decomposition.

    A bullet bond-like instrument where the total yield is decomposed
    into risk-free rate, credit spread, illiquidity spread, and other
    spread.  Present value is discounted at the risk-free rate by
    default, reflecting the illiquidity premium as excess income.

    Parameters
    ----------
    face_value : float
        Par / face value.
    maturity : int
        Years to maturity.
    risk_free_rate : float
        Risk-free rate component (decimal).
    credit_spread : float
        Credit spread component (decimal).
    illiquidity_spread : float
        Illiquidity premium component (decimal).
    other_spread : float
        Any other spread component (decimal).
    frequency : int
        Coupon payments per year (default 2 = semi-annual).
    rating : str or None
        Optional credit rating label.
    """

    face_value: float
    maturity: int
    risk_free_rate: float
    credit_spread: float
    illiquidity_spread: float
    other_spread: float
    frequency: int = 2
    rating: str | None = None

    @property
    def total_yield(self) -> float:
        """Total yield = sum of all spread components."""
        return (
            self.risk_free_rate + self.credit_spread + self.illiquidity_spread + self.other_spread
        )

    @property
    def n_periods(self) -> int:
        return self.maturity * self.frequency

    @property
    def coupon(self) -> float:
        """Per-period coupon based on total yield."""
        return self.face_value * self.total_yield / self.frequency

    def cashflows(self) -> pl.DataFrame:
        """Return the cash-flow schedule.

        Columns: period, coupon, principal, total.
        """
        n = self.n_periods
        c = self.coupon

        periods = list(range(1, n + 1))
        coupons = [c] * n
        principals = [0.0] * (n - 1) + [self.face_value]
        totals = [c + p for c, p in zip(coupons, principals, strict=True)]

        return pl.DataFrame(
            {
                "period": periods,
                "coupon": coupons,
                "principal": principals,
                "total": totals,
            }
        )

    def present_value(self, discount_rate: float | None = None) -> float:
        """PV discounted at the risk-free rate (default) or a given rate.

        When discount_rate is None, uses self.risk_free_rate.
        Discounting at the risk-free rate while earning the total yield
        reflects the illiquidity premium as excess value.
        """
        rate = discount_rate if discount_rate is not None else self.risk_free_rate
        r = rate / self.frequency
        cf = self.cashflows()
        pv = sum(total / (1 + r) ** t for t, total in zip(cf["period"], cf["total"], strict=True))
        if pv < 0:
            logger.warning("PrivateCredit PV is negative (%.2f)", pv)
        return pv

    def duration(self, discount_rate: float | None = None) -> float:
        """Macaulay duration in years."""
        rate = discount_rate if discount_rate is not None else self.risk_free_rate
        r = rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(rate)

        weighted = sum(
            (t / self.frequency) * total / (1 + r) ** t
            for t, total in zip(cf["period"], cf["total"], strict=True)
        )
        return weighted / pv

    def convexity(self, discount_rate: float | None = None) -> float:
        """Convexity (in years squared)."""
        rate = discount_rate if discount_rate is not None else self.risk_free_rate
        r = rate / self.frequency
        cf = self.cashflows()
        pv = self.present_value(rate)

        conv = sum(
            t * (t + 1) * total / (1 + r) ** (t + 2)
            for t, total in zip(cf["period"], cf["total"], strict=True)
        )
        return conv / (pv * self.frequency**2)
