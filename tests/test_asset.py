"""Tests for alm.asset module (Bond, Mortgage)."""

import polars as pl
import pytest

from alm.asset import Bond, Mortgage

# ---------------------------------------------------------------------------
# Bond
# ---------------------------------------------------------------------------


class TestBond:
    """Tests for the Bond class."""

    @pytest.fixture()
    def bond(self) -> Bond:
        """3-year, 5 % semi-annual coupon, $1 000 face."""
        return Bond(face_value=1_000, coupon_rate=0.05, maturity=3, frequency=2)

    def test_n_periods(self, bond: Bond):
        assert bond.n_periods == 6

    def test_coupon(self, bond: Bond):
        assert bond.coupon == pytest.approx(25.0)

    def test_cashflows_shape(self, bond: Bond):
        cf = bond.cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert cf.shape == (6, 4)
        assert cf.columns == ["period", "coupon", "principal", "total"]

    def test_cashflows_last_period_includes_principal(self, bond: Bond):
        cf = bond.cashflows()
        last = cf.row(-1, named=True)
        assert last["principal"] == pytest.approx(1_000.0)
        assert last["total"] == pytest.approx(1_025.0)

    def test_cashflows_interior_principal_is_zero(self, bond: Bond):
        cf = bond.cashflows()
        interior = cf.filter(pl.col("period") < bond.n_periods)
        assert interior["principal"].sum() == pytest.approx(0.0)

    def test_pv_at_par_rate(self, bond: Bond):
        """PV at the coupon rate should equal par."""
        assert bond.present_value(0.05) == pytest.approx(1_000.0, rel=1e-6)

    def test_pv_higher_rate_below_par(self, bond: Bond):
        assert bond.present_value(0.08) < 1_000.0

    def test_pv_lower_rate_above_par(self, bond: Bond):
        assert bond.present_value(0.02) > 1_000.0

    def test_duration_positive(self, bond: Bond):
        d = bond.duration(0.05)
        assert d > 0
        assert d < bond.maturity

    def test_convexity_positive(self, bond: Bond):
        assert bond.convexity(0.05) > 0


# ---------------------------------------------------------------------------
# Mortgage
# ---------------------------------------------------------------------------


class TestMortgage:
    """Tests for the Mortgage class."""

    @pytest.fixture()
    def mortgage(self) -> Mortgage:
        """$100 000, 6 %, 3-year, monthly."""
        return Mortgage(principal=100_000, annual_rate=0.06, term=3, frequency=12)

    def test_n_periods(self, mortgage: Mortgage):
        assert mortgage.n_periods == 36

    def test_payment_positive(self, mortgage: Mortgage):
        assert mortgage.payment > 0

    def test_cashflows_shape(self, mortgage: Mortgage):
        cf = mortgage.cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert cf.shape == (36, 5)
        assert cf.columns == ["period", "payment", "interest", "principal", "balance"]

    def test_final_balance_is_zero(self, mortgage: Mortgage):
        cf = mortgage.cashflows()
        assert cf["balance"][-1] == pytest.approx(0.0, abs=0.01)

    def test_balance_at_matches_schedule(self, mortgage: Mortgage):
        cf = mortgage.cashflows()
        for t in [1, 12, 36]:
            assert mortgage.balance_at(t) == pytest.approx(
                cf.row(t - 1, named=True)["balance"], rel=1e-6
            )

    def test_pv_at_contract_rate(self, mortgage: Mortgage):
        """PV at the contract rate should equal the original principal."""
        assert mortgage.present_value(0.06) == pytest.approx(100_000.0, rel=1e-6)

    def test_duration_positive(self, mortgage: Mortgage):
        d = mortgage.duration(0.06)
        assert d > 0
        assert d < mortgage.term

    def test_convexity_positive(self, mortgage: Mortgage):
        assert mortgage.convexity(0.06) > 0
