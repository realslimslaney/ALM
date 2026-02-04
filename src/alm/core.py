"""Core ALM instruments for duration management."""

import logging
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


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
            ncf / (1 + r) ** t
            for t, ncf in zip(cf["period"], cf["net_cashflow"], strict=True)
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
