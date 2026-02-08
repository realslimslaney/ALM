"""Functions for reading financial data from external sources."""

import logging
import os
from datetime import date
from pathlib import Path

import polars as pl
from dotenv import load_dotenv
from fredapi import Fred

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

load_dotenv()

# US Treasury constant-maturity series on FRED
_TREASURY_SERIES: dict[str, str] = {
    "1M": "DGS1MO",
    "3M": "DGS3MO",
    "6M": "DGS6MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "3Y": "DGS3",
    "5Y": "DGS5",
    "7Y": "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}


def _get_fred() -> Fred:
    """Return a Fred client using the FRED_API_KEY environment variable."""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise OSError(
            "FRED_API_KEY not set. Copy .env.example to .env and add your key. "
            "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    return Fred(api_key=api_key)


def read_treasury_rates(
    start: str | date | None = None,
    end: str | date | None = None,
    tenors: list[str] | None = None,
) -> pl.DataFrame:
    """Fetch US Treasury constant-maturity rates from FRED.

    Parameters
    ----------
    start : str or date, optional
        Start date (inclusive). Defaults to all available history.
    end : str or date, optional
        End date (inclusive). Defaults to today.
    tenors : list of str, optional
        Which tenors to fetch, e.g. ["1Y", "5Y", "10Y"].
        Defaults to all available tenors.

    Returns
    -------
    pl.DataFrame
        Columns: date, plus one column per tenor (e.g. "1M", "10Y")
        with rates as percentages.
    """
    fred = _get_fred()
    tenors = tenors or list(_TREASURY_SERIES.keys())

    invalid = set(tenors) - _TREASURY_SERIES.keys()
    if invalid:
        raise ValueError(
            f"Unknown tenors: {invalid}. Valid tenors: {list(_TREASURY_SERIES.keys())}"
        )

    frames: list[pl.DataFrame] = []
    for tenor in tenors:
        series = fred.get_series(
            _TREASURY_SERIES[tenor],
            observation_start=start,
            observation_end=end,
        )
        df = pl.DataFrame({"date": series.index, tenor: series.values})
        frames.append(df)

    result = frames[0]
    for df in frames[1:]:
        result = result.join(df, on="date", how="full", coalesce=True)

    return result.sort("date")


def read_mortality_table(sex: str) -> pl.DataFrame:
    """Read a SOA IAM 2012 Basic mortality table CSV for a given sex.

    Parameters
    ----------
    sex : str
        "male" or "female".

    Returns
    -------
    pl.DataFrame
        Columns: age (Int64), sex (str), qx (Float64).
    """
    sex = sex.lower()
    if sex not in ("male", "female"):
        raise ValueError(f"sex must be 'male' or 'female', got '{sex}'")

    path = _DATA_DIR / "soa_tables" / f"iam_2012_{sex}_basic_anb.csv"
    df = pl.read_csv(path)
    result = df.rename({sex: "qx"}).with_columns(pl.lit(sex).alias("sex"))

    out_of_range = result.filter((pl.col("qx") < 0) | (pl.col("qx") > 1))
    if len(out_of_range) > 0:
        logger.warning(
            "Mortality table '%s' has %d qx values outside [0, 1]",
            sex,
            len(out_of_range),
        )

    return result


def get_2012_iam_table() -> pl.DataFrame:
    """Read and combine male and female SOA IAM 2012 Basic mortality tables.

    Returns
    -------
    pl.DataFrame
        Long-format table with columns: age (Int64), sex (str), qx (Float64).
    """
    male = read_mortality_table("male")
    female = read_mortality_table("female")
    return pl.concat([male, female]).sort("age", "sex")
