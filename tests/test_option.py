"""Tests for alm.option module (CallOption, PutOption, standalone BSM functions).

Reference values taken from Hull, *Options, Futures & Other Derivatives*, 10th ed.,
and verified against the standard BSM closed-form formula.
"""

import math

import pytest

from alm.option import CallOption, PutOption, bs_call, bs_greeks, bs_put, implied_vol

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Hull Example 15.6 (approx): S=42, K=40, T=0.5, r=0.10, σ=0.20, q=0
HULL_PARAMS = dict(S=42.0, K=40.0, T=0.5, r=0.10, sigma=0.20, q=0.0)
HULL_CALL_PRICE = 4.76  # Hull p.338 (rounded)
HULL_PUT_PRICE = 0.81  # via put-call parity

# ATM params for symmetry / parity tests
ATM = dict(S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20, q=0.0)
ATM_WITH_DIV = dict(S=100.0, K=100.0, T=1.0, r=0.05, sigma=0.20, q=0.03)


# ---------------------------------------------------------------------------
# Standalone: bs_call / bs_put
# ---------------------------------------------------------------------------


class TestBsCall:
    def test_hull_example(self):
        p = HULL_PARAMS
        price = bs_call(p["S"], p["K"], p["T"], p["r"], p["sigma"], p["q"])
        assert price == pytest.approx(HULL_CALL_PRICE, abs=0.01)

    def test_zero_time_itm(self):
        assert bs_call(110, 100, 0.0, 0.05, 0.20) == pytest.approx(10.0)

    def test_zero_time_otm(self):
        assert bs_call(90, 100, 0.0, 0.05, 0.20) == pytest.approx(0.0)

    def test_price_positive(self):
        assert bs_call(**{k: v for k, v in ATM.items() if k != "q"}) > 0

    def test_increases_with_spot(self):
        p = ATM
        c1 = bs_call(90, p["K"], p["T"], p["r"], p["sigma"], p["q"])
        c2 = bs_call(110, p["K"], p["T"], p["r"], p["sigma"], p["q"])
        assert c2 > c1

    def test_decreases_with_strike(self):
        p = ATM
        c1 = bs_call(p["S"], 90, p["T"], p["r"], p["sigma"], p["q"])
        c2 = bs_call(p["S"], 110, p["T"], p["r"], p["sigma"], p["q"])
        assert c1 > c2

    def test_dividend_yield_reduces_call(self):
        p = ATM
        c_no_div = bs_call(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.0)
        c_div = bs_call(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.03)
        assert c_no_div > c_div


class TestBsPut:
    def test_hull_example(self):
        p = HULL_PARAMS
        price = bs_put(p["S"], p["K"], p["T"], p["r"], p["sigma"], p["q"])
        assert price == pytest.approx(HULL_PUT_PRICE, abs=0.01)

    def test_zero_time_itm(self):
        assert bs_put(90, 100, 0.0, 0.05, 0.20) == pytest.approx(10.0)

    def test_zero_time_otm(self):
        assert bs_put(110, 100, 0.0, 0.05, 0.20) == pytest.approx(0.0)

    def test_price_positive(self):
        assert bs_put(**{k: v for k, v in ATM.items() if k != "q"}) > 0

    def test_dividend_yield_increases_put(self):
        p = ATM
        put_no_div = bs_put(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.0)
        put_div = bs_put(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.03)
        assert put_div > put_no_div


# ---------------------------------------------------------------------------
# Put-call parity
# ---------------------------------------------------------------------------


class TestPutCallParity:
    """C - P = S·e^(-qT) - K·e^(-rT) for European options (Merton form)."""

    @pytest.mark.parametrize("params", [ATM, ATM_WITH_DIV, HULL_PARAMS])
    def test_parity(self, params):
        S, K, T, r, sigma, q = (
            params["S"],
            params["K"],
            params["T"],
            params["r"],
            params["sigma"],
            params["q"],
        )
        call = bs_call(S, K, T, r, sigma, q)
        put = bs_put(S, K, T, r, sigma, q)
        lhs = call - put
        rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert lhs == pytest.approx(rhs, rel=1e-6)


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------


class TestBsGreeks:
    @pytest.fixture()
    def greeks(self):
        p = ATM
        return bs_greeks(p["S"], p["K"], p["T"], p["r"], p["sigma"], p["q"])

    def test_call_delta_in_range(self, greeks):
        assert 0 < greeks["call_delta"] < 1

    def test_put_delta_in_range(self, greeks):
        assert -1 < greeks["put_delta"] < 0

    def test_call_put_delta_sum(self, greeks):
        """call_delta + |put_delta| ≈ e^(-qT) for q=0 → ≈ 1."""
        assert greeks["call_delta"] + abs(greeks["put_delta"]) == pytest.approx(1.0, rel=1e-6)

    def test_gamma_positive(self, greeks):
        assert greeks["gamma"] > 0

    def test_vega_positive(self, greeks):
        assert greeks["vega"] > 0

    def test_call_theta_negative(self, greeks):
        """Long call loses value as time passes (all else equal)."""
        assert greeks["call_theta"] < 0

    def test_put_theta_negative(self, greeks):
        """Long put typically loses value with time for standard params."""
        assert greeks["put_theta"] < 0

    def test_call_rho_positive(self, greeks):
        """Call value rises with interest rates."""
        assert greeks["call_rho"] > 0

    def test_put_rho_negative(self, greeks):
        """Put value falls as interest rates rise."""
        assert greeks["put_rho"] < 0

    def test_zero_time_greeks(self):
        p = ATM
        g = bs_greeks(p["S"], p["K"], 0.0, p["r"], p["sigma"], p["q"])
        assert g["gamma"] == pytest.approx(0.0)
        assert g["vega"] == pytest.approx(0.0)

    def test_dividend_yield_reduces_call_delta(self):
        p = ATM
        g_no_div = bs_greeks(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.0)
        g_div = bs_greeks(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.05)
        assert g_no_div["call_delta"] > g_div["call_delta"]


# ---------------------------------------------------------------------------
# Implied volatility
# ---------------------------------------------------------------------------


class TestImpliedVol:
    @pytest.mark.parametrize("sigma", [0.10, 0.20, 0.30, 0.50])
    def test_round_trip_call(self, sigma):
        """Imply vol back from BSM call price; should recover the input σ."""
        p = ATM
        price = bs_call(p["S"], p["K"], p["T"], p["r"], sigma, p["q"])
        iv = implied_vol(price, p["S"], p["K"], p["T"], p["r"], "call", p["q"])
        assert iv == pytest.approx(sigma, rel=1e-4)

    @pytest.mark.parametrize("sigma", [0.10, 0.20, 0.30, 0.50])
    def test_round_trip_put(self, sigma):
        p = ATM
        price = bs_put(p["S"], p["K"], p["T"], p["r"], sigma, p["q"])
        iv = implied_vol(price, p["S"], p["K"], p["T"], p["r"], "put", p["q"])
        assert iv == pytest.approx(sigma, rel=1e-4)

    def test_invalid_option_type(self):
        with pytest.raises(ValueError, match="option_type"):
            implied_vol(5.0, 100, 100, 1.0, 0.05, "forward")

    def test_arbitrage_price_raises(self):
        """A price of 0 for an ITM call with no time value should fail."""
        with pytest.raises(ValueError):
            implied_vol(0.0, 110, 100, 1.0, 0.05, "call")


# ---------------------------------------------------------------------------
# CallOption class
# ---------------------------------------------------------------------------


class TestCallOption:
    @pytest.fixture()
    def call(self) -> CallOption:
        p = ATM
        return CallOption(
            spot=p["S"],
            strike=p["K"],
            time_to_expiry=p["T"],
            risk_free_rate=p["r"],
            volatility=p["sigma"],
        )

    def test_price_matches_bs_call(self, call):
        p = ATM
        assert call.price() == pytest.approx(
            bs_call(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.0)
        )

    def test_delta_is_call_delta(self, call):
        assert call.delta() == pytest.approx(call.greeks()["call_delta"])

    def test_delta_in_range(self, call):
        assert 0 < call.delta() < 1

    def test_gamma_positive(self, call):
        assert call.gamma() > 0

    def test_vega_positive(self, call):
        assert call.vega() > 0

    def test_theta_negative(self, call):
        assert call.theta() < 0

    def test_rho_positive(self, call):
        assert call.rho() > 0

    def test_implied_vol_round_trip(self, call):
        iv = call.implied_vol(call.price())
        assert iv == pytest.approx(call.volatility, rel=1e-4)

    def test_dividend_yield_field(self):
        c = CallOption(
            spot=100,
            strike=100,
            time_to_expiry=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.03,
        )
        c_no_div = CallOption(
            spot=100,
            strike=100,
            time_to_expiry=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
        )
        assert c.price() < c_no_div.price()


# ---------------------------------------------------------------------------
# PutOption class
# ---------------------------------------------------------------------------


class TestPutOption:
    @pytest.fixture()
    def put(self) -> PutOption:
        p = ATM
        return PutOption(
            spot=p["S"],
            strike=p["K"],
            time_to_expiry=p["T"],
            risk_free_rate=p["r"],
            volatility=p["sigma"],
        )

    def test_price_matches_bs_put(self, put):
        p = ATM
        assert put.price() == pytest.approx(bs_put(p["S"], p["K"], p["T"], p["r"], p["sigma"], 0.0))

    def test_delta_is_put_delta(self, put):
        assert put.delta() == pytest.approx(put.greeks()["put_delta"])

    def test_delta_in_range(self, put):
        assert -1 < put.delta() < 0

    def test_gamma_positive(self, put):
        assert put.gamma() > 0

    def test_vega_positive(self, put):
        assert put.vega() > 0

    def test_theta_negative(self, put):
        assert put.theta() < 0

    def test_rho_negative(self, put):
        assert put.rho() < 0

    def test_implied_vol_round_trip(self, put):
        iv = put.implied_vol(put.price())
        assert iv == pytest.approx(put.volatility, rel=1e-4)

    def test_put_call_parity_via_classes(self):
        """C - P should equal S·e^(-qT) - K·e^(-rT)."""
        p = ATM
        call = CallOption(
            spot=p["S"],
            strike=p["K"],
            time_to_expiry=p["T"],
            risk_free_rate=p["r"],
            volatility=p["sigma"],
        )
        put = PutOption(
            spot=p["S"],
            strike=p["K"],
            time_to_expiry=p["T"],
            risk_free_rate=p["r"],
            volatility=p["sigma"],
        )
        lhs = call.price() - put.price()
        rhs = p["S"] * math.exp(0) - p["K"] * math.exp(-p["r"] * p["T"])
        assert lhs == pytest.approx(rhs, rel=1e-6)
