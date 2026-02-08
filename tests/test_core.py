"""Tests for alm.core module (InterestRateSwap, hedging utilities, SAA)."""

import polars as pl
import pytest

from alm.asset import Bond
from alm.core import (
    SAA,
    InterestRateSwap,
    default_saa,
    dollar_convexity,
    dv01,
    immunize,
    irr,
    spia_saa,
    term_saa,
)


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

    def test_cashflows_year_column(self, swap: InterestRateSwap, flat_floating: list[float]):
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

    def test_pay_fixed_positive_when_floating_exceeds_fixed(self, swap: InterestRateSwap):
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

    def test_duration_returns_float(self, swap: InterestRateSwap, flat_floating: list[float]):
        assert isinstance(swap.duration(flat_floating, 0.04), float)

    def test_convexity_returns_float(self, swap: InterestRateSwap, flat_floating: list[float]):
        assert isinstance(swap.convexity(flat_floating, 0.04), float)

    # ---- dv01 -------------------------------------------------------------

    def test_dv01_pay_fixed_negative(self, swap: InterestRateSwap, flat_floating: list[float]):
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


# ===================================================================
# Tests for dv01() standalone function
# ===================================================================


class TestDV01:
    """Tests for the standalone dv01() helper."""

    def test_bond_dv01_positive(self):
        """A long bond position gains value when rates fall → positive DV01."""
        bond = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=10, frequency=2)
        result = dv01(bond.present_value, 0.05)
        assert result > 0

    def test_dv01_increases_with_maturity(self):
        """Longer maturity bonds have higher DV01."""
        short = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=5, frequency=2)
        long = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=30, frequency=2)
        assert dv01(long.present_value, 0.05) > dv01(short.present_value, 0.05)

    def test_dv01_matches_swap_method(self):
        """Standalone dv01() on a swap PV wrapper should match Swap.dv01()."""
        swap = InterestRateSwap(
            notional=1_000_000, fixed_rate=0.04, tenor=5, frequency=2, pay_fixed=False
        )
        flat = [0.04] * swap.n_periods

        # Wrap swap PV so both floating rates and discount rate shift together
        def swap_pv(r: float) -> float:
            return swap.present_value([r] * swap.n_periods, r)

        assert dv01(swap_pv, 0.04) == pytest.approx(swap.dv01(flat, 0.04), rel=1e-4)


# ===================================================================
# Tests for dollar_convexity() standalone function
# ===================================================================


class TestDollarConvexity:
    """Tests for the standalone dollar_convexity() helper."""

    def test_bond_dollar_convexity_positive(self):
        """Option-free bonds have positive dollar convexity."""
        bond = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=10, frequency=2)
        assert dollar_convexity(bond.present_value, 0.05) > 0

    def test_dollar_convexity_increases_with_maturity(self):
        """Longer maturity bonds have higher dollar convexity."""
        short = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=5, frequency=2)
        long = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=30, frequency=2)
        dc_short = dollar_convexity(short.present_value, 0.05)
        dc_long = dollar_convexity(long.present_value, 0.05)
        assert dc_long > dc_short

    def test_zero_coupon_higher_convexity_than_coupon(self):
        """A zero-coupon bond has higher convexity than a coupon bond
        of the same maturity and face value."""
        zc = Bond(face_value=1_000_000, coupon_rate=0.0, maturity=10, frequency=2)
        coupon = Bond(face_value=1_000_000, coupon_rate=0.05, maturity=10, frequency=2)
        # Compare convexity per dollar of PV (normalised)
        dc_zc = dollar_convexity(zc.present_value, 0.05) / zc.present_value(0.05)
        dc_cp = dollar_convexity(coupon.present_value, 0.05) / coupon.present_value(0.05)
        assert dc_zc > dc_cp


# ===================================================================
# Tests for immunize() function
# ===================================================================


class TestImmunize:
    """Tests for the immunize() 2×2 solver."""

    def test_known_solution(self):
        """Verify against a hand-computed example."""
        # System:  4*n1 + 8*n2 = 500
        #         20*n1 + 90*n2 = 80_000
        n1, n2 = immunize(
            dd_gap=500,
            dc_gap=80_000,
            dd_per_unit_1=4.0,
            dc_per_unit_1=20.0,
            dd_per_unit_2=8.0,
            dc_per_unit_2=90.0,
        )
        # Check solution satisfies both equations
        assert 4.0 * n1 + 8.0 * n2 == pytest.approx(500)
        assert 20.0 * n1 + 90.0 * n2 == pytest.approx(80_000)

    def test_zero_gaps(self):
        """When both gaps are zero, notionals should be zero."""
        n1, n2 = immunize(
            dd_gap=0,
            dc_gap=0,
            dd_per_unit_1=4.0,
            dc_per_unit_1=20.0,
            dd_per_unit_2=8.0,
            dc_per_unit_2=90.0,
        )
        assert n1 == pytest.approx(0.0)
        assert n2 == pytest.approx(0.0)

    def test_duration_only_gap(self):
        """When only duration gap exists, convexity equation still holds."""
        n1, n2 = immunize(
            dd_gap=1000,
            dc_gap=0,
            dd_per_unit_1=5.0,
            dc_per_unit_1=30.0,
            dd_per_unit_2=10.0,
            dc_per_unit_2=100.0,
        )
        assert 5.0 * n1 + 10.0 * n2 == pytest.approx(1000)
        assert 30.0 * n1 + 100.0 * n2 == pytest.approx(0)

    def test_singular_matrix_raises(self):
        """Linearly dependent instruments should raise ValueError."""
        with pytest.raises(ValueError, match="linearly dependent"):
            immunize(
                dd_gap=100,
                dc_gap=200,
                dd_per_unit_1=4.0,
                dc_per_unit_1=20.0,
                dd_per_unit_2=8.0,
                dc_per_unit_2=40.0,  # 2× instrument 1
            )

    def test_negative_notional_allowed(self):
        """Negative notional (short position) is a valid solution."""
        n1, n2 = immunize(
            dd_gap=100,
            dc_gap=-500,
            dd_per_unit_1=5.0,
            dc_per_unit_1=50.0,
            dd_per_unit_2=10.0,
            dc_per_unit_2=20.0,
        )
        assert 5.0 * n1 + 10.0 * n2 == pytest.approx(100)
        assert 50.0 * n1 + 20.0 * n2 == pytest.approx(-500)


# ===================================================================
# Tests for SAA class
# ===================================================================


class TestSAA:
    """Tests for the SAA class."""

    def test_valid_weights(self):
        saa = SAA(weights={"govt_bonds": 0.5, "corp_bonds": 0.5})
        assert sum(saa.weights.values()) == pytest.approx(1.0)

    def test_weights_not_summing_to_one_raises(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            SAA(weights={"govt_bonds": 0.5, "corp_bonds": 0.4})

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="negative"):
            SAA(weights={"a": -0.1, "b": 1.1})

    def test_private_credit_over_10_pct_raises(self):
        with pytest.raises(ValueError, match="10%"):
            SAA(weights={"govt_bonds": 0.5, "private_credit": 0.5})

    def test_private_credit_at_10_pct_ok(self):
        saa = SAA(weights={"govt_bonds": 0.9, "private_credit": 0.10})
        assert saa.weights["private_credit"] == 0.10

    def test_allocation_method(self):
        saa = SAA(weights={"govt_bonds": 0.6, "corp_bonds": 0.4})
        alloc = saa.allocation(1_000_000)
        assert alloc["govt_bonds"] == pytest.approx(600_000)
        assert alloc["corp_bonds"] == pytest.approx(400_000)

    def test_default_saa(self):
        saa = default_saa()
        assert sum(saa.weights.values()) == pytest.approx(1.0)
        assert saa.weights["private_credit"] <= 0.10

    def test_spia_saa(self):
        saa = spia_saa()
        assert sum(saa.weights.values()) == pytest.approx(1.0)
        assert saa.weights["govt_bonds"] >= 0.50

    def test_term_saa(self):
        saa = term_saa()
        assert sum(saa.weights.values()) == pytest.approx(1.0)
        assert saa.weights["mortgages"] >= 0.30


# ===================================================================
# Tests for irr() function
# ===================================================================


class TestIRR:
    """Tests for the irr() internal rate of return function."""

    def test_simple_one_period(self):
        """Invest 100, receive 110 in 1 year → IRR = 10%."""
        assert irr([-100, 110]) == pytest.approx(0.10, abs=1e-8)

    def test_zero_coupon_bond(self):
        """Invest 1000, receive 1000*(1.05)^5 in 5 years → IRR = 5%."""
        fv = 1000 * 1.05**5
        cfs = [-1000, 0, 0, 0, 0, fv]
        assert irr(cfs) == pytest.approx(0.05, abs=1e-8)

    def test_level_annuity(self):
        """Bond-like: invest 1000, receive 50/yr for 10 yrs + 1000 at maturity."""
        cfs = [-1000] + [50] * 9 + [1050]
        assert irr(cfs) == pytest.approx(0.05, abs=1e-8)

    def test_npv_at_irr_is_zero(self):
        """Verify that NPV evaluated at the computed IRR ≈ 0."""
        cfs = [-500, 100, 150, 200, 150]
        r = irr(cfs)
        npv = sum(cf / (1 + r) ** t for t, cf in enumerate(cfs))
        assert npv == pytest.approx(0.0, abs=1e-8)

    def test_non_convergence_raises(self):
        """All-positive cashflows have no real IRR; should raise."""
        with pytest.raises(ValueError, match="did not converge"):
            irr([100, 100, 100], max_iter=50)
