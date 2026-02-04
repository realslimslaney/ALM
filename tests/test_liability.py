"""Tests for alm.liability module (SPIA, WL, Term, FIA)."""

import polars as pl
import pytest

from alm.liability import FIA, SPIA, WL, Term

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_qx(rate: float, years: int) -> list[float]:
    """Return a flat mortality-rate vector."""
    return [rate] * years


# ---------------------------------------------------------------------------
# SPIA
# ---------------------------------------------------------------------------


class TestSPIA:
    """Tests for the SPIA class."""

    @pytest.fixture()
    def spia(self) -> SPIA:
        """$100 000 premium, $6 000/yr payout, 30-year horizon, monthly."""
        return SPIA(
            premium=100_000,
            annual_payout=6_000,
            qx=_flat_qx(0.01, 30),
            frequency=12,
            certain_period=0,
        )

    def test_cashflows_shape(self, spia: SPIA):
        cf = spia.cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert cf.shape == (360, 5)
        assert "expected_payout" in cf.columns

    def test_expected_payout_decreases_over_time(self, spia: SPIA):
        """With mortality, expected payouts should decrease."""
        cf = spia.cashflows()
        first = cf["expected_payout"][0]
        last = cf["expected_payout"][-1]
        assert last < first

    def test_certain_period_guarantees_full_payout(self):
        spia_cp = SPIA(
            premium=100_000,
            annual_payout=6_000,
            qx=_flat_qx(0.05, 10),
            frequency=12,
            certain_period=5,
        )
        cf = spia_cp.cashflows()
        certain_rows = cf.filter(pl.col("year") <= 5.0)
        pmt = 6_000 / 12
        assert all(
            v == pytest.approx(pmt) for v in certain_rows["expected_payout"].to_list()
        )

    def test_pv_positive(self, spia: SPIA):
        assert spia.present_value(0.05) > 0

    def test_duration_positive(self, spia: SPIA):
        d = spia.duration(0.05)
        assert d > 0

    def test_convexity_positive(self, spia: SPIA):
        assert spia.convexity(0.05) > 0


# ---------------------------------------------------------------------------
# WL – Whole Life
# ---------------------------------------------------------------------------


class TestWL:
    """Tests for the WL class."""

    @pytest.fixture()
    def wl(self) -> WL:
        return WL(
            face_value=100_000,
            annual_premium=1_200,
            qx=_flat_qx(0.01, 30),
            frequency=12,
        )

    def test_cashflows_shape(self, wl: WL):
        cf = wl.cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert cf.shape == (360, 6)
        assert "net_cashflow" in cf.columns

    def test_cashflows_columns(self, wl: WL):
        cf = wl.cashflows()
        expected = [
            "period",
            "year",
            "survival_prob",
            "expected_premium",
            "expected_benefit",
            "net_cashflow",
        ]
        assert cf.columns == expected

    def test_pv_returns_float(self, wl: WL):
        assert isinstance(wl.present_value(0.05), float)

    def test_duration_returns_float(self, wl: WL):
        assert isinstance(wl.duration(0.05), float)

    def test_convexity_returns_float(self, wl: WL):
        assert isinstance(wl.convexity(0.05), float)


# ---------------------------------------------------------------------------
# Term
# ---------------------------------------------------------------------------


class TestTerm:
    """Tests for the Term class."""

    @pytest.fixture()
    def term(self) -> Term:
        return Term(
            face_value=500_000,
            annual_premium=600,
            term=20,
            qx=_flat_qx(0.005, 30),
            frequency=12,
        )

    def test_cashflows_shape(self, term: Term):
        cf = term.cashflows()
        assert cf.shape == (240, 6)

    def test_cashflows_limited_to_term(self, term: Term):
        """Cashflows stop at the policy term, even though qx is longer."""
        cf = term.cashflows()
        assert cf["year"].max() == pytest.approx(20.0)

    def test_pv_returns_float(self, term: Term):
        assert isinstance(term.present_value(0.05), float)

    def test_duration_positive(self, term: Term):
        assert term.duration(0.05) > 0

    def test_convexity_returns_float(self, term: Term):
        assert isinstance(term.convexity(0.05), float)


# ---------------------------------------------------------------------------
# FIA – Fixed Indexed Annuity
# ---------------------------------------------------------------------------


class TestFIA:
    """Tests for the FIA class."""

    @pytest.fixture()
    def fia(self) -> FIA:
        return FIA(
            premium=100_000,
            term=7,
            qx=_flat_qx(0.01, 10),
            floor=0.0,
            cap=0.06,
            participation_rate=1.0,
        )

    def test_credited_rate_floor(self, fia: FIA):
        assert fia.credited_rate(-0.10) == 0.0

    def test_credited_rate_cap(self, fia: FIA):
        assert fia.credited_rate(0.20) == 0.06

    def test_credited_rate_passthrough(self, fia: FIA):
        assert fia.credited_rate(0.03) == pytest.approx(0.03)

    def test_account_values_shape(self, fia: FIA):
        rates = [0.04] * 7
        av = fia.account_values(rates)
        assert isinstance(av, pl.DataFrame)
        assert av.shape == (8, 4)  # year 0 through 7

    def test_account_values_grow(self, fia: FIA):
        rates = [0.04] * 7
        av = fia.account_values(rates)
        vals = av["account_value"].to_list()
        assert all(vals[i + 1] > vals[i] for i in range(len(vals) - 1))

    def test_cashflows_shape(self, fia: FIA):
        rates = [0.04] * 7
        cf = fia.cashflows(rates)
        assert cf.shape == (7, 7)

    def test_maturity_benefit_only_on_last_year(self, fia: FIA):
        rates = [0.04] * 7
        cf = fia.cashflows(rates)
        mat = cf["expected_maturity_benefit"].to_list()
        assert all(v == 0.0 for v in mat[:-1])
        assert mat[-1] > 0

    def test_pv_positive(self, fia: FIA):
        rates = [0.04] * 7
        assert fia.present_value(rates, 0.05) > 0

    def test_duration_positive(self, fia: FIA):
        rates = [0.04] * 7
        assert fia.duration(rates, 0.05) > 0

    def test_convexity_positive(self, fia: FIA):
        rates = [0.04] * 7
        assert fia.convexity(rates, 0.05) > 0
