"""Tests for alm.liability module."""

import logging

import polars as pl
import pytest

from alm.liability import FIA, SPIA, WL, Term, _survival_prob, _validate_qx, qx_from_table

from .conftest import flat_qx

# ---------------------------------------------------------------------------
# qx_from_table
# ---------------------------------------------------------------------------


class TestQxFromTable:
    """Tests for the qx_from_table helper."""

    @pytest.fixture()
    def mort_table(self) -> pl.DataFrame:
        """Small mortality table with both sexes."""
        return pl.DataFrame(
            {
                "age": [60, 61, 62, 60, 61, 62],
                "sex": ["male", "male", "male", "female", "female", "female"],
                "qx": [0.01, 0.012, 0.015, 0.008, 0.009, 0.011],
            }
        )

    def test_returns_list_of_floats(self, mort_table: pl.DataFrame):
        result = qx_from_table(mort_table, age=60, sex="male")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_filters_by_age(self, mort_table: pl.DataFrame):
        result = qx_from_table(mort_table, age=61, sex="male")
        assert len(result) == 2
        assert result[0] == pytest.approx(0.012)

    def test_filters_by_sex(self, mort_table: pl.DataFrame):
        male = qx_from_table(mort_table, age=60, sex="male")
        female = qx_from_table(mort_table, age=60, sex="female")
        assert male[0] == pytest.approx(0.01)
        assert female[0] == pytest.approx(0.008)

    def test_sex_case_insensitive(self, mort_table: pl.DataFrame):
        result = qx_from_table(mort_table, age=60, sex="Male")
        assert len(result) == 3

    def test_no_sex_filter(self):
        """When sex is None, returns all rows at or above the given age."""
        table = pl.DataFrame({"age": [50, 51, 52], "qx": [0.005, 0.006, 0.007]})
        result = qx_from_table(table, age=51)
        assert len(result) == 2

    def test_empty_result_raises(self, mort_table: pl.DataFrame):
        with pytest.raises(ValueError, match="No rows"):
            qx_from_table(mort_table, age=100, sex="male")


# ---------------------------------------------------------------------------
# _validate_qx
# ---------------------------------------------------------------------------


class TestValidateQx:
    """Tests for the _validate_qx helper."""

    def test_valid_qx_no_warnings(self, caplog):
        with caplog.at_level(logging.WARNING, logger="alm.liability"):
            _validate_qx([0.0, 0.01, 0.1, 0.5])
        assert caplog.text == ""

    def test_qx_above_one_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="alm.liability"):
            _validate_qx([1.5])
        assert "outside [0, 1]" in caplog.text

    def test_qx_below_zero_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="alm.liability"):
            _validate_qx([-0.1])
        assert "outside [0, 1]" in caplog.text

    def test_qx_above_half_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="alm.liability"):
            _validate_qx([0.6])
        assert "unusually high" in caplog.text

    def test_empty_list_no_warnings(self, caplog):
        with caplog.at_level(logging.WARNING, logger="alm.liability"):
            _validate_qx([])
        assert caplog.text == ""


# ---------------------------------------------------------------------------
# _survival_prob
# ---------------------------------------------------------------------------


class TestSurvivalProb:
    """Tests for the _survival_prob helper."""

    def test_t_zero_returns_one(self):
        assert _survival_prob([0.1, 0.2], 0) == pytest.approx(1.0)

    def test_one_year(self):
        assert _survival_prob([0.1], 1.0) == pytest.approx(0.9)

    def test_two_years(self):
        assert _survival_prob([0.1, 0.1], 2.0) == pytest.approx(0.81)

    def test_fractional_year_udd(self):
        """UDD: S(0.5) = 1 - 0.5 * 0.1 = 0.95."""
        assert _survival_prob([0.1], 0.5) == pytest.approx(0.95)

    def test_zero_mortality_returns_one(self):
        assert _survival_prob([0.0, 0.0, 0.0], 3.0) == pytest.approx(1.0)

    def test_certain_death(self):
        assert _survival_prob([1.0], 1.0) == pytest.approx(0.0)

    @pytest.mark.parametrize(
        ("qx", "t", "expected"),
        [
            ([0.05], 1.0, 0.95),
            ([0.05, 0.10], 2.0, 0.855),
            ([0.0, 0.0], 1.5, 1.0),
        ],
    )
    def test_parametrized_cases(self, qx, t, expected):
        assert _survival_prob(qx, t) == pytest.approx(expected)

    def test_t_beyond_qx_len(self):
        """Beyond len(qx), no further mortality is applied."""
        sp_at_end = _survival_prob([0.1], 1.0)
        sp_beyond = _survival_prob([0.1], 5.0)
        assert sp_beyond == pytest.approx(sp_at_end)


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
            qx=flat_qx(0.01, 30),
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
            qx=flat_qx(0.05, 10),
            frequency=12,
            certain_period=5,
        )
        cf = spia_cp.cashflows()
        certain_rows = cf.filter(pl.col("year") <= 5.0)
        pmt = 6_000 / 12
        assert all(v == pytest.approx(pmt) for v in certain_rows["expected_payout"].to_list())

    def test_pv_positive(self, spia: SPIA):
        assert spia.present_value(0.05) > 0

    def test_duration_positive(self, spia: SPIA):
        d = spia.duration(0.05)
        assert d > 0

    def test_convexity_positive(self, spia: SPIA):
        assert spia.convexity(0.05) > 0

    def test_immortal_expected_payout_constant(self):
        """Zero mortality means every expected payout equals the per-period amount."""
        spia = SPIA(
            premium=100_000,
            annual_payout=12_000,
            qx=flat_qx(0.0, 10),
            frequency=12,
            certain_period=0,
        )
        cf = spia.cashflows()
        pmt = 12_000 / 12
        assert all(v == pytest.approx(pmt) for v in cf["expected_payout"].to_list())

    def test_certain_death_zeroes_payout(self):
        """qx=1 means survival probability drops to zero immediately."""
        spia = SPIA(
            premium=100_000,
            annual_payout=6_000,
            qx=flat_qx(1.0, 5),
            frequency=12,
            certain_period=0,
        )
        cf = spia.cashflows()
        # After the first year, expected payouts should be essentially zero
        late = cf.filter(pl.col("year") > 1.0)
        assert all(v == pytest.approx(0.0, abs=1e-10) for v in late["expected_payout"].to_list())


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
            qx=flat_qx(0.01, 30),
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

    # --- WL.from_face tests ---

    def test_from_face_returns_wl(self):
        qx = flat_qx(0.01, 30)
        wl = WL.from_face(face_value=100_000, qx=qx, discount_rate=0.05)
        assert isinstance(wl, WL)
        assert wl.face_value == 100_000

    def test_from_face_premium_positive(self):
        qx = flat_qx(0.01, 30)
        wl = WL.from_face(face_value=100_000, qx=qx, discount_rate=0.05)
        assert wl.annual_premium > 0

    def test_from_face_equivalence_principle(self):
        """PV of net cashflows at the pricing rate should be approximately zero."""
        qx = flat_qx(0.01, 30)
        wl = WL.from_face(face_value=100_000, qx=qx, discount_rate=0.05)
        pv = wl.present_value(0.05)
        assert pv == pytest.approx(0.0, abs=1.0)

    def test_from_face_higher_mortality_higher_premium(self):
        """Higher mortality should produce a higher premium."""
        low = WL.from_face(face_value=100_000, qx=flat_qx(0.005, 30), discount_rate=0.05)
        high = WL.from_face(face_value=100_000, qx=flat_qx(0.02, 30), discount_rate=0.05)
        assert high.annual_premium > low.annual_premium

    def test_from_face_age_passthrough(self):
        qx = flat_qx(0.01, 30)
        wl = WL.from_face(face_value=100_000, qx=qx, discount_rate=0.05, age=45)
        assert wl.age == 45


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
            qx=flat_qx(0.005, 30),
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
            qx=flat_qx(0.01, 10),
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
