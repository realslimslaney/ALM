"""Tests for alm.read module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest

from alm.read import (
    _ASSUMPTIONS_DIR,
    _CREDIT_SPREAD_SERIES,
    _TREASURY_SERIES,
    _get_fred,
    get_2012_iam_table,
    get_credit_spreads,
    get_spread,
    read_credit_spread_indices,
    read_mortality_table,
    read_treasury_rates,
    update_credit_spreads,
)


# ---------- _get_fred ----------
def test_get_fred_missing_key(monkeypatch):
    """Raises OSError when FRED_API_KEY is not set."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(OSError, match="FRED_API_KEY not set"):
        _get_fred()


@patch("alm.read.Fred")
def test_get_fred_with_key(mock_fred_cls, monkeypatch):
    """Returns a Fred client when the key is present."""
    monkeypatch.setenv("FRED_API_KEY", "test_key")
    client = _get_fred()
    mock_fred_cls.assert_called_once_with(api_key="test_key")
    assert client == mock_fred_cls.return_value


# ---------- read_treasury_rates ----------
def _make_mock_series(dates, values):
    """Helper: build a pandas Series with a DatetimeIndex."""
    return pd.Series(values, index=pd.DatetimeIndex(dates))


def _patch_fred(series_map: dict[str, pd.Series]):
    """Return a mock Fred whose get_series dispatches by series ID."""
    mock_fred = MagicMock()
    mock_fred.get_series.side_effect = lambda sid, **kw: series_map[sid]
    return patch("alm.read._get_fred", return_value=mock_fred)


class TestReadTreasuryRates:
    """Tests for read_treasury_rates."""

    def test_invalid_tenor_raises(self):
        """Unknown tenors raise ValueError."""
        with _patch_fred({}), pytest.raises(ValueError, match="Unknown tenors"):
            read_treasury_rates(tenors=["99Y"])

    def test_single_tenor(self):
        """Fetches a single tenor and returns correct shape."""
        dates = ["2025-01-02", "2025-01-03"]
        series_map = {"DGS10": _make_mock_series(dates, [4.5, 4.6])}

        with _patch_fred(series_map):
            df = read_treasury_rates(start="2025-01-02", end="2025-01-03", tenors=["10Y"])

        assert isinstance(df, pl.DataFrame)
        assert df.columns == ["date", "10Y"]
        assert df.shape == (2, 2)

    def test_multiple_tenors_joined(self):
        """Multiple tenors are joined on date."""
        dates = ["2025-01-02", "2025-01-03"]
        series_map = {
            "DGS2": _make_mock_series(dates, [4.0, 4.1]),
            "DGS10": _make_mock_series(dates, [4.5, 4.6]),
        }

        with _patch_fred(series_map):
            df = read_treasury_rates(tenors=["2Y", "10Y"])

        assert set(df.columns) == {"date", "2Y", "10Y"}
        assert df.shape == (2, 3)

    def test_result_sorted_by_date(self):
        """Output is sorted by date even if input is not."""
        dates_reversed = ["2025-01-05", "2025-01-02"]
        series_map = {"DGS5": _make_mock_series(dates_reversed, [3.9, 3.8])}

        with _patch_fred(series_map):
            df = read_treasury_rates(tenors=["5Y"])

        date_col = df.get_column("date").to_list()
        assert date_col == sorted(date_col)

    def test_defaults_to_all_tenors(self):
        """When tenors=None, all tenors in _TREASURY_SERIES are fetched."""
        dates = ["2025-01-02"]
        series_map = {sid: _make_mock_series(dates, [4.0]) for sid in _TREASURY_SERIES.values()}

        with _patch_fred(series_map) as mock:
            df = read_treasury_rates(tenors=None)
            calls = mock.return_value.get_series.call_args_list

        assert len(calls) == len(_TREASURY_SERIES)
        assert set(df.columns) == {"date"} | _TREASURY_SERIES.keys()

    def test_start_end_passed_through(self):
        """start and end are forwarded to Fred.get_series."""
        dates = ["2025-06-01"]
        series_map = {"DGS1": _make_mock_series(dates, [5.0])}

        with _patch_fred(series_map) as mock:
            read_treasury_rates(start=date(2025, 6, 1), end="2025-06-30", tenors=["1Y"])
            _, kwargs = mock.return_value.get_series.call_args

        assert kwargs["observation_start"] == date(2025, 6, 1)
        assert kwargs["observation_end"] == "2025-06-30"


# ---------- read_mortality_table ----------
class TestReadMortalityTable:
    """Tests for read_mortality_table."""

    def test_invalid_sex_raises(self):
        with pytest.raises(ValueError, match="must be 'male' or 'female'"):
            read_mortality_table("other")

    def test_male_table_shape_and_columns(self):
        df = read_mortality_table("male")
        assert df.columns == ["age", "qx", "sex"]
        assert df.shape[0] == 121
        assert df["sex"].unique().to_list() == ["male"]

    def test_female_table_shape_and_columns(self):
        df = read_mortality_table("female")
        assert df.columns == ["age", "qx", "sex"]
        assert df.shape[0] == 121
        assert df["sex"].unique().to_list() == ["female"]

    def test_case_insensitive(self):
        df = read_mortality_table("Male")
        assert df["sex"].unique().to_list() == ["male"]

    def test_age_range(self):
        df = read_mortality_table("male")
        assert df["age"].min() == 0
        assert df["age"].max() == 120

    def test_qx_values_between_0_and_1(self):
        df = read_mortality_table("male")
        assert df["qx"].min() > 0
        assert df["qx"].max() <= 1


# ---------- get_2012_iam_table ----------
class TestGet2012IamTable:
    """Tests for get_2012_iam_table."""

    def test_combined_shape(self):
        df = get_2012_iam_table()
        assert df.shape == (242, 3)

    def test_combined_columns(self):
        df = get_2012_iam_table()
        assert df.columns == ["age", "qx", "sex"]

    def test_both_sexes_present(self):
        df = get_2012_iam_table()
        assert sorted(df["sex"].unique().to_list()) == ["female", "male"]

    def test_sorted_by_age_and_sex(self):
        df = get_2012_iam_table()
        ages = df["age"].to_list()
        assert ages == sorted(ages)


# ---------- get_credit_spreads ----------
class TestGetCreditSpreads:
    """Tests for get_credit_spreads."""

    def test_loads_dataframe(self):
        df = get_credit_spreads()
        assert isinstance(df, pl.DataFrame)
        assert "rating" in df.columns

    def test_expected_ratings(self):
        df = get_credit_spreads()
        ratings = df["rating"].to_list()
        assert ratings == ["AAA", "AA", "A", "BBB", "BB", "B"]

    def test_spreads_increase_with_lower_rating(self):
        """Lower-rated bonds should have wider spreads at every tenor."""
        df = get_credit_spreads()
        for col in df.columns:
            if col == "rating":
                continue
            values = df[col].to_list()
            assert values == sorted(values), f"Spreads not monotonically increasing for tenor {col}"

    def test_has_standard_tenors(self):
        df = get_credit_spreads()
        tenor_cols = [c for c in df.columns if c != "rating"]
        assert len(tenor_cols) >= 6


# ---------- get_spread ----------
class TestGetSpread:
    """Tests for get_spread lookup."""

    def test_exact_match(self):
        spread = get_spread("AAA", 5)
        assert spread == 30 / 10_000  # 30 bps

    def test_interpolation(self):
        """Maturity 4 should interpolate between 3 and 5."""
        spread_3 = get_spread("A", 3)
        spread_5 = get_spread("A", 5)
        spread_4 = get_spread("A", 4)
        assert spread_3 < spread_4 < spread_5

    def test_interpolation_value(self):
        """Midpoint of A-rated 3Y (60 bps) and 5Y (85 bps) = 72.5 bps."""
        spread = get_spread("A", 4)
        assert abs(spread - 0.00725) < 1e-6

    def test_unknown_rating_raises(self):
        with pytest.raises(ValueError, match="Unknown rating"):
            get_spread("CCC", 5)

    def test_beyond_max_tenor(self):
        """Maturity beyond table max uses the longest tenor."""
        spread_30 = get_spread("BBB", 30)
        spread_50 = get_spread("BBB", 50)
        assert spread_50 == spread_30

    def test_below_min_tenor(self):
        """Maturity below table min uses the shortest tenor."""
        spread_1 = get_spread("BBB", 1)
        # Maturity 0 isn't meaningful but should not crash
        assert get_spread("BBB", 0) == spread_1


# ---------- read_credit_spread_indices ----------
class TestReadCreditSpreadIndices:
    """Tests for read_credit_spread_indices."""

    def test_invalid_series_raises(self):
        """Unknown series names raise ValueError."""
        with _patch_fred({}), pytest.raises(ValueError, match="Unknown series"):
            read_credit_spread_indices(series=["FAKE"])

    def test_single_series(self):
        """Fetches a single series and returns correct shape."""
        dates = ["2025-01-02", "2025-01-03"]
        series_map = {"BAMLC0A0CM": _make_mock_series(dates, [1.5, 1.6])}

        with _patch_fred(series_map):
            df = read_credit_spread_indices(series=["IG_OAS"])

        assert isinstance(df, pl.DataFrame)
        assert df.columns == ["date", "IG_OAS"]
        assert df.shape == (2, 2)

    def test_multiple_series_joined(self):
        """Multiple series are joined on date."""
        dates = ["2025-01-02", "2025-01-03"]
        series_map = {
            "BAMLC0A0CM": _make_mock_series(dates, [1.5, 1.6]),
            "AAA10Y": _make_mock_series(dates, [0.5, 0.6]),
        }

        with _patch_fred(series_map):
            df = read_credit_spread_indices(series=["IG_OAS", "AAA10Y"])

        assert set(df.columns) == {"date", "IG_OAS", "AAA10Y"}
        assert df.shape == (2, 3)

    def test_defaults_to_all_series(self):
        """When series=None, all four series are fetched."""
        dates = ["2025-01-02"]
        series_map = {
            sid: _make_mock_series(dates, [1.0]) for sid in _CREDIT_SPREAD_SERIES.values()
        }

        with _patch_fred(series_map) as mock:
            df = read_credit_spread_indices()
            calls = mock.return_value.get_series.call_args_list

        assert len(calls) == len(_CREDIT_SPREAD_SERIES)
        assert set(df.columns) == {"date"} | _CREDIT_SPREAD_SERIES.keys()

    def test_result_sorted_by_date(self):
        """Output is sorted by date even if input is not."""
        dates = ["2025-01-05", "2025-01-02"]
        series_map = {"AAA10Y": _make_mock_series(dates, [0.5, 0.4])}

        with _patch_fred(series_map):
            df = read_credit_spread_indices(series=["AAA10Y"])

        date_col = df.get_column("date").to_list()
        assert date_col == sorted(date_col)

    def test_start_end_passed_through(self):
        """start and end are forwarded to Fred.get_series."""
        dates = ["2025-06-01"]
        series_map = {"BAA10Y": _make_mock_series(dates, [2.0])}

        with _patch_fred(series_map) as mock:
            read_credit_spread_indices(start=date(2025, 6, 1), end="2025-06-30", series=["BAA10Y"])
            _, kwargs = mock.return_value.get_series.call_args

        assert kwargs["observation_start"] == date(2025, 6, 1)
        assert kwargs["observation_end"] == "2025-06-30"


# ---------- update_credit_spreads ----------
def _mock_fred_for_update():
    """Return a context-manager patch with known spread values."""
    mock_fred = MagicMock()
    # Values in percentage points (×100 → bps)
    # AAA10Y=0.60→60 bps, IG_OAS=1.50→150 bps,
    # BAA10Y=2.50→250 bps, HY_OAS=5.00→500 bps
    series_data = {
        "AAA10Y": pd.Series([0.60]),
        "BAMLC0A0CM": pd.Series([1.50]),
        "BAA10Y": pd.Series([2.50]),
        "BAMLH0A0HYM2": pd.Series([5.00]),
    }
    mock_fred.get_series.side_effect = lambda sid, **kw: series_data[sid]
    return patch("alm.read._get_fred", return_value=mock_fred)


class TestUpdateCreditSpreads:
    """Tests for update_credit_spreads."""

    def test_anchored_ratings_at_10y(self, tmp_path, monkeypatch):
        """10-year values for anchored ratings match FRED data exactly."""
        import shutil

        shutil.copy(
            _ASSUMPTIONS_DIR / "credit_spreads.csv",
            tmp_path / "credit_spreads.csv",
        )
        monkeypatch.setattr("alm.read._ASSUMPTIONS_DIR", tmp_path)

        with _mock_fred_for_update():
            result = update_credit_spreads()

        assert result.filter(pl.col("rating") == "AAA")["10"].item() == 60
        assert result.filter(pl.col("rating") == "A")["10"].item() == 150
        assert result.filter(pl.col("rating") == "BBB")["10"].item() == 250
        assert result.filter(pl.col("rating") == "BB")["10"].item() == 500

    def test_aa_interpolated(self, tmp_path, monkeypatch):
        """AA is interpolated between AAA and A."""
        import shutil

        shutil.copy(
            _ASSUMPTIONS_DIR / "credit_spreads.csv",
            tmp_path / "credit_spreads.csv",
        )
        monkeypatch.setattr("alm.read._ASSUMPTIONS_DIR", tmp_path)

        with _mock_fred_for_update():
            result = update_credit_spreads()

        aa_10 = result.filter(pl.col("rating") == "AA")["10"].item()
        aaa_10 = result.filter(pl.col("rating") == "AAA")["10"].item()
        a_10 = result.filter(pl.col("rating") == "A")["10"].item()
        # AA must sit between AAA and A
        assert aaa_10 < aa_10 < a_10

    def test_b_extrapolated(self, tmp_path, monkeypatch):
        """B is extrapolated from BB using the original ratio."""
        import shutil

        shutil.copy(
            _ASSUMPTIONS_DIR / "credit_spreads.csv",
            tmp_path / "credit_spreads.csv",
        )
        monkeypatch.setattr("alm.read._ASSUMPTIONS_DIR", tmp_path)

        with _mock_fred_for_update():
            result = update_credit_spreads()

        bb_10 = result.filter(pl.col("rating") == "BB")["10"].item()
        b_10 = result.filter(pl.col("rating") == "B")["10"].item()
        # Original ratio: B(650)/BB(420) ≈ 1.548
        assert b_10 > bb_10
        expected = round(500 * 650 / 420)
        assert b_10 == expected

    def test_spreads_monotonically_increasing(self, tmp_path, monkeypatch):
        """Lower-rated bonds still have wider spreads at every tenor."""
        import shutil

        shutil.copy(
            _ASSUMPTIONS_DIR / "credit_spreads.csv",
            tmp_path / "credit_spreads.csv",
        )
        monkeypatch.setattr("alm.read._ASSUMPTIONS_DIR", tmp_path)

        with _mock_fred_for_update():
            result = update_credit_spreads()

        for col in result.columns:
            if col == "rating":
                continue
            values = result[col].to_list()
            assert values == sorted(values), f"Spreads not monotonically increasing for tenor {col}"

    def test_csv_written(self, tmp_path, monkeypatch):
        """Result is persisted to the credit_spreads.csv file."""
        import shutil

        shutil.copy(
            _ASSUMPTIONS_DIR / "credit_spreads.csv",
            tmp_path / "credit_spreads.csv",
        )
        monkeypatch.setattr("alm.read._ASSUMPTIONS_DIR", tmp_path)

        with _mock_fred_for_update():
            result = update_credit_spreads()

        written = pl.read_csv(tmp_path / "credit_spreads.csv")
        assert written.shape == result.shape
        assert written["rating"].to_list() == result["rating"].to_list()

    def test_preserves_rating_order(self, tmp_path, monkeypatch):
        """Output keeps the original rating order."""
        import shutil

        shutil.copy(
            _ASSUMPTIONS_DIR / "credit_spreads.csv",
            tmp_path / "credit_spreads.csv",
        )
        monkeypatch.setattr("alm.read._ASSUMPTIONS_DIR", tmp_path)

        with _mock_fred_for_update():
            result = update_credit_spreads()

        assert result["rating"].to_list() == [
            "AAA",
            "AA",
            "A",
            "BBB",
            "BB",
            "B",
        ]
