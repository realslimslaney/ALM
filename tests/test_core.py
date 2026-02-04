"""Tests for alm.core module (InterestRateSwap)."""

import polars as pl
import pytest

from alm.core import InterestRateSwap


class TestInterestRateSwap:
    """Tests for the InterestRateSwap class."""

    @pytest.fixture()
    def swap(self) -> InterestRateSwap:
        """5-year pay-fixed swap, 4 % fixed, semi-annual, $1M notional."""
        return InterestRateSwap(
            notional=1_000_000,
            fixed_rate=0.04,
            tenor=5,
            frequency=2,
            pay_fixed=True,
        )

    @pytest.fixture()
    def flat_floating(self, swap: InterestRateSwap) -> list[float]:
        """Flat floating rate at 3.5 % for every period."""
        return [0.035] * swap.n_periods

    # ---- structure --------------------------------------------------------

    def test_n_periods(self, swap: InterestRateSwap):
        assert swap.n_periods == 10

    def test_cashflows_shape(self, swap: InterestRateSwap, flat_floating: list[float]):
        cf = swap.cashflows(flat_floating)
        assert isinstance(cf, pl.DataFrame)
        assert cf.shape == (10, 5)
        assert cf.columns == [
            "period",
            "year",
            "fixed_leg",
            "floating_leg",
            "net_cashflow",
        ]

    def test_cashflows_year_column(
        self, swap: InterestRateSwap, flat_floating: list[float]
    ):
        cf = swap.cashflows(flat_floating)
        assert cf["year"][0] == pytest.approx(0.5)
        assert cf["year"][-1] == pytest.approx(5.0)

    # ---- pay-fixed net cashflow signs -------------------------------------

    def test_pay_fixed_negative_when_fixed_exceeds_floating(
        self, swap: InterestRateSwap, flat_floating: list[float]
    ):
        """Pay-fixed: when fixed > floating, net is negative (net outflow)."""
        cf = swap.cashflows(flat_floating)
        assert all(v < 0 for v in cf["net_cashflow"].to_list())

    def test_pay_fixed_positive_when_floating_exceeds_fixed(
        self, swap: InterestRateSwap
    ):
        high_float = [0.06] * swap.n_periods
        cf = swap.cashflows(high_float)
        assert all(v > 0 for v in cf["net_cashflow"].to_list())

    # ---- at-the-money swap ------------------------------------------------

    def test_atm_pv_is_zero(self, swap: InterestRateSwap):
        """When floating == fixed every period, PV should be zero."""
        atm = [swap.fixed_rate] * swap.n_periods
        assert swap.present_value(atm, swap.fixed_rate) == pytest.approx(0.0, abs=1e-6)

    # ---- pay vs receive symmetry ------------------------------------------

    def test_pv_symmetry(self, swap: InterestRateSwap, flat_floating: list[float]):
        """Receive-fixed PV should be the negative of pay-fixed PV."""
        rcv = InterestRateSwap(
            notional=swap.notional,
            fixed_rate=swap.fixed_rate,
            tenor=swap.tenor,
            frequency=swap.frequency,
            pay_fixed=False,
        )
        pv_pay = swap.present_value(flat_floating, 0.04)
        pv_rcv = rcv.present_value(flat_floating, 0.04)
        assert pv_pay == pytest.approx(-pv_rcv, rel=1e-10)

    def test_dv01_symmetry(self, swap: InterestRateSwap, flat_floating: list[float]):
        rcv = InterestRateSwap(
            notional=swap.notional,
            fixed_rate=swap.fixed_rate,
            tenor=swap.tenor,
            frequency=swap.frequency,
            pay_fixed=False,
        )
        assert swap.dv01(flat_floating, 0.04) == pytest.approx(
            -rcv.dv01(flat_floating, 0.04), rel=1e-10
        )

    # ---- duration / convexity ---------------------------------------------

    def test_duration_returns_float(
        self, swap: InterestRateSwap, flat_floating: list[float]
    ):
        assert isinstance(swap.duration(flat_floating, 0.04), float)

    def test_convexity_returns_float(
        self, swap: InterestRateSwap, flat_floating: list[float]
    ):
        assert isinstance(swap.convexity(flat_floating, 0.04), float)

    # ---- dv01 -------------------------------------------------------------

    def test_dv01_pay_fixed_negative(
        self, swap: InterestRateSwap, flat_floating: list[float]
    ):
        """Pay-fixed swap loses value when rates fall → negative DV01."""
        assert swap.dv01(flat_floating, 0.04) < 0

    def test_dv01_receive_fixed_positive(self, flat_floating: list[float]):
        """Receive-fixed swap gains value when rates fall → positive DV01."""
        rcv = InterestRateSwap(
            notional=1_000_000,
            fixed_rate=0.04,
            tenor=5,
            frequency=2,
            pay_fixed=False,
        )
        assert rcv.dv01(flat_floating, 0.04) > 0
