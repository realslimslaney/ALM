"""Tests for alm.asset module (Bond, Mortgage, PrivateCredit)."""

import polars as pl
import pytest

from alm.asset import Bond, Mortgage, PrivateCredit

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

    def test_default_rating_is_none(self):
        bond = Bond(face_value=1000, coupon_rate=0.05, maturity=3)
        assert bond.rating is None
        assert bond.credit_spread == 0.0

    def test_with_rating(self):
        bond = Bond(
            face_value=1000,
            coupon_rate=0.05,
            maturity=3,
            rating="AA",
            credit_spread=0.005,
        )
        assert bond.rating == "AA"
        assert bond.credit_spread == 0.005
        # PV still uses passed discount_rate, not credit_spread
        pv = bond.present_value(0.05)
        assert pv == pytest.approx(1000.0, rel=1e-6)


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


# ---------------------------------------------------------------------------
# PrivateCredit
# ---------------------------------------------------------------------------


class TestPrivateCredit:
    """Tests for the PrivateCredit class."""

    @pytest.fixture()
    def pc(self) -> PrivateCredit:
        """5-year PC: 4% rfr + 1.5% credit + 2% illiquidity + 0.5% other = 8%."""
        return PrivateCredit(
            face_value=1_000,
            maturity=5,
            risk_free_rate=0.04,
            credit_spread=0.015,
            illiquidity_spread=0.020,
            other_spread=0.005,
        )

    def test_total_yield(self, pc: PrivateCredit):
        assert pc.total_yield == pytest.approx(0.08)

    def test_n_periods(self, pc: PrivateCredit):
        assert pc.n_periods == 10

    def test_coupon(self, pc: PrivateCredit):
        # 1000 * 0.08 / 2 = 40.0
        assert pc.coupon == pytest.approx(40.0)

    def test_cashflows_shape(self, pc: PrivateCredit):
        cf = pc.cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert cf.shape == (10, 4)
        assert cf.columns == ["period", "coupon", "principal", "total"]

    def test_cashflows_last_period_includes_principal(self, pc: PrivateCredit):
        cf = pc.cashflows()
        last = cf.row(-1, named=True)
        assert last["principal"] == pytest.approx(1_000.0)

    def test_pv_at_risk_free_above_par(self, pc: PrivateCredit):
        """PV discounted at risk-free exceeds par (coupon > discount)."""
        pv = pc.present_value()
        assert pv > 1_000.0

    def test_pv_at_total_yield_equals_par(self, pc: PrivateCredit):
        """PV at the total yield should equal par."""
        pv = pc.present_value(pc.total_yield)
        assert pv == pytest.approx(1_000.0, rel=1e-6)

    def test_pv_explicit_rate_overrides_default(self, pc: PrivateCredit):
        pv_explicit = pc.present_value(0.06)
        pv_default = pc.present_value()
        assert pv_explicit != pytest.approx(pv_default)

    def test_duration_positive(self, pc: PrivateCredit):
        d = pc.duration()
        assert d > 0
        assert d < pc.maturity

    def test_convexity_positive(self, pc: PrivateCredit):
        assert pc.convexity() > 0
