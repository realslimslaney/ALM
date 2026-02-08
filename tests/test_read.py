"""Tests for alm.read module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest

from alm.read import (
    _TREASURY_SERIES,
    _get_fred,
    get_2012_iam_table,
    read_mortality_table,
    read_treasury_rates,
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
