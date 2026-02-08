"""Core ALM instruments and hedging utilities."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

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
