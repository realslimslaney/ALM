"""Shared fixtures and helpers for the ALM test suite."""

import polars as pl
import pytest

from alm.asset import Bond


def flat_qx(rate: float, years: int) -> list[float]:
    """Return a flat mortality-rate vector."""
    return [rate] * years


def make_mortality(min_age: int = 30, max_age: int = 120) -> pl.DataFrame:
    """Build a simple synthetic mortality table for testing."""
    rows = []
    for age in range(min_age, max_age + 1):
        for sex in ["male", "female"]:
            qx = min(0.001 * 1.05 ** (age - min_age), 1.0)
            rows.append({"age": age, "sex": sex, "qx": qx})
    return pl.DataFrame(rows)


@pytest.fixture()
def sample_df() -> pl.DataFrame:
    """Simple DataFrame for chart tests."""
    return pl.DataFrame(
        {
            "year": [1, 2, 3, 4],
            "assets": [100.0, 105.0, 110.0, 115.0],
            "liabilities": [90.0, 92.0, 95.0, 98.0],
            "group": ["A", "A", "B", "B"],
        }
    )


@pytest.fixture()
def sample_bond() -> Bond:
    """Standard 3-year, 5% semi-annual coupon, $1000 face bond."""
    return Bond(face_value=1000, coupon_rate=0.05, maturity=3, frequency=2)


@pytest.fixture()
def sample_qx() -> list[float]:
    """Flat 1% mortality for 30 years."""
    return flat_qx(0.01, 30)
