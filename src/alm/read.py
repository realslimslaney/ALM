"""Functions for reading financial data from external sources."""

import logging
import os
from datetime import date
from pathlib import Path

import polars as pl
from dotenv import load_dotenv
from fredapi import Fred

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _PROJECT_ROOT / "data"
_ASSUMPTIONS_DIR = _PROJECT_ROOT / "assumptions"

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

# FRED credit-spread index series
_CREDIT_SPREAD_SERIES: dict[str, str] = {
    "IG_OAS": "BAMLC0A0CM",
    "HY_OAS": "BAMLH0A0HYM2",
    "BAA10Y": "BAA10Y",
    "AAA10Y": "AAA10Y",
}

# Which FRED label anchors each rating at the 10-year point
_SPREAD_ANCHORS: dict[str, str] = {
    "AAA": "AAA10Y",
    "A": "IG_OAS",
    "BBB": "BAA10Y",
    "BB": "HY_OAS",
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


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


def get_credit_spreads() -> pl.DataFrame:
    """Load the static credit spread curve from assumptions/credit_spreads.csv.

    Returns
    -------
    pl.DataFrame
        Columns: rating (str), plus one column per maturity tenor
        (e.g. "1", "3", "5", "10") with spreads in basis points.
    """
    path = _ASSUMPTIONS_DIR / "credit_spreads.csv"
    return pl.read_csv(path)


def get_spread(rating: str, maturity: int) -> float:
    """Look up the credit spread for a given rating and maturity.

    If the exact maturity is not in the table, linearly interpolates
    between the two nearest tenors.

    Parameters
    ----------
    rating : str
        Credit rating (e.g. "AAA", "BBB", "BB").
    maturity : int
        Bond maturity in years.

    Returns
    -------
    float
        Credit spread as a decimal (e.g. 0.0150 for 150 bps).
    """
    df = get_credit_spreads()
    row = df.filter(pl.col("rating") == rating)
    if row.is_empty():
        raise ValueError(f"Unknown rating '{rating}'. Available: {df['rating'].to_list()}")

    tenors = sorted(int(c) for c in df.columns if c != "rating")
    # Exact match
    if maturity in tenors:
        bps = row[str(maturity)].item()
        return bps / 10_000

    # Interpolate
    lower = (
        max(t for t in tenors if t <= maturity) if any(t <= maturity for t in tenors) else tenors[0]
    )
    upper = (
        min(t for t in tenors if t >= maturity)
        if any(t >= maturity for t in tenors)
        else tenors[-1]
    )

    if lower == upper:
        return row[str(lower)].item() / 10_000

    bps_lo = row[str(lower)].item()
    bps_hi = row[str(upper)].item()
    frac = (maturity - lower) / (upper - lower)
    return (bps_lo + frac * (bps_hi - bps_lo)) / 10_000


def get_treasury_rates(refresh: bool = False) -> pl.DataFrame:
    """Load US Treasury rates, fetching from FRED on first call.

    On first call (or when ``refresh=True``), fetches the latest rates
    from FRED and caches them to ``assumptions/treasury_rates.csv``.
    Subsequent calls read from the cached file.

    Parameters
    ----------
    refresh : bool
        If True, re-fetch from FRED even if a cached file exists.

    Returns
    -------
    pl.DataFrame
        Columns: date, plus one column per tenor with rates as percentages.
    """
    path = _ASSUMPTIONS_DIR / "treasury_rates.csv"

    if not refresh and path.exists():
        logger.info("Reading cached treasury rates from %s", path)
        return pl.read_csv(path, try_parse_dates=True)

    logger.info("Fetching treasury rates from FRED...")
    df = read_treasury_rates()
    _ASSUMPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(path)
    logger.info("Saved treasury rates to %s (%d rows)", path, len(df))
    return df


# ---------------------------------------------------------------------------
# Credit-spread indices from FRED
# ---------------------------------------------------------------------------


def read_credit_spread_indices(
    start: str | date | None = None,
    end: str | date | None = None,
    series: list[str] | None = None,
) -> pl.DataFrame:
    """Fetch credit spread indices from FRED.

    Available series
    ----------------
    IG_OAS   -- ICE BofA US Corporate Investment Grade OAS (BAMLC0A0CM)
    HY_OAS   -- ICE BofA US High Yield OAS (BAMLH0A0HYM2)
    BAA10Y   -- Moody's Baa yield relative to 10-Year Treasury
    AAA10Y   -- Moody's Aaa yield relative to 10-Year Treasury

    Parameters
    ----------
    start : str or date, optional
        Start date (inclusive).
    end : str or date, optional
        End date (inclusive).
    series : list of str, optional
        Which series to fetch (e.g. ``["IG_OAS", "BAA10Y"]``).
        Defaults to all four.

    Returns
    -------
    pl.DataFrame
        Columns: date, plus one column per series with spreads
        in percentage points.
    """
    fred = _get_fred()
    series = series or list(_CREDIT_SPREAD_SERIES.keys())

    invalid = set(series) - _CREDIT_SPREAD_SERIES.keys()
    if invalid:
        raise ValueError(
            f"Unknown series: {invalid}. Valid series: {list(_CREDIT_SPREAD_SERIES.keys())}"
        )

    frames: list[pl.DataFrame] = []
    for label in series:
        s = fred.get_series(
            _CREDIT_SPREAD_SERIES[label],
            observation_start=start,
            observation_end=end,
        )
        df = pl.DataFrame({"date": s.index, label: s.values})
        frames.append(df)

    result = frames[0]
    for df in frames[1:]:
        result = result.join(df, on="date", how="full", coalesce=True)

    return result.sort("date")


def update_credit_spreads() -> pl.DataFrame:
    """Update the credit spread curve using the latest FRED market data.

    Fetches the most recent value for four FRED credit-spread series and
    maps them to 10-year anchor points in the credit spread table:

    ==========  ================  ================================
    Rating      FRED series       Description
    ==========  ================  ================================
    AAA         AAA10Y            Aaa yield minus 10-Year Treasury
    A           BAMLC0A0CM        ICE BofA IG OAS
    BBB         BAA10Y            Baa yield minus 10-Year Treasury
    BB          BAMLH0A0HYM2      ICE BofA HY OAS
    ==========  ================  ================================

    For each anchored rating the entire tenor curve is scaled by
    ``new_10Y / old_10Y``.  Non-anchored ratings are interpolated:

    * **AA** -- linearly interpolated between AAA and A at each tenor,
      preserving the relative position from the original table.
    * **B** -- extrapolated from BB using the original BB/B ratio
      at each tenor.

    The result is rounded to whole basis points and written to
    ``assumptions/credit_spreads.csv``.

    If ``FRED_API_KEY`` is not set, the existing CSV is returned unchanged.

    Returns
    -------
    pl.DataFrame
        The updated credit spread table.
    """
    try:
        fred = _get_fred()
    except OSError:
        logger.warning("FRED_API_KEY not set — using existing credit spreads")
        return get_credit_spreads()

    # Fetch the latest non-null value for each anchor series
    anchor_bps: dict[str, float] = {}
    for rating, label in _SPREAD_ANCHORS.items():
        series_id = _CREDIT_SPREAD_SERIES[label]
        s = fred.get_series(series_id)
        latest = s.dropna().iloc[-1]
        anchor_bps[rating] = float(latest) * 100  # pct pts -> bps
        logger.info("  %s (%s): %.0f bps", label, rating, anchor_bps[rating])

    # Load the current table
    df = get_credit_spreads()
    tenors = [c for c in df.columns if c != "rating"]
    ratings = df["rating"].to_list()

    # Helper: extract one row as {tenor: value}
    def _row_dict(r: str) -> dict[str, float]:
        row = df.filter(pl.col("rating") == r)
        return {t: float(row[t].item()) for t in tenors}

    old = {r: _row_dict(r) for r in ratings}

    # Scale anchored ratings by new_10Y / old_10Y
    new: dict[str, dict[str, int]] = {}
    for rating in ("AAA", "A", "BBB", "BB"):
        old_10 = old[rating]["10"]
        scale = anchor_bps[rating] / old_10
        new[rating] = {t: round(old[rating][t] * scale) for t in tenors}

    # Interpolate AA between AAA and A (preserve relative position)
    new["AA"] = {}
    for t in tenors:
        old_aaa = old["AAA"][t]
        old_aa = old["AA"][t]
        old_a = old["A"][t]
        span = old_a - old_aaa
        weight = (old_aa - old_aaa) / span if span else 0.5
        new["AA"][t] = round(new["AAA"][t] + weight * (new["A"][t] - new["AAA"][t]))

    # Extrapolate B from BB (preserve old BB/B ratio)
    new["B"] = {}
    for t in tenors:
        ratio = old["B"][t] / old["BB"][t]
        new["B"][t] = round(new["BB"][t] * ratio)

    # Assemble DataFrame in original rating order
    rows = [{"rating": r, **new[r]} for r in ratings]
    result = pl.DataFrame(rows)

    # Write back
    path = _ASSUMPTIONS_DIR / "credit_spreads.csv"
    _ASSUMPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    result.write_csv(path)
    logger.info("Updated credit spreads at %s", path)

    return result
