"""Tests for the alm package's public API surface."""

import pytest

import alm


class TestPackageAPI:
    """Verify the alm package exports all expected symbols."""

    def test_import_not_none(self):
        assert alm is not None

    @pytest.mark.parametrize(
        "symbol",
        [
            "Bond",
            "Mortgage",
            "PrivateCredit",
            "SAA",
            "Block",
            "InterestRateSwap",
            "default_saa",
            "dollar_convexity",
            "dv01",
            "immunize",
            "irr",
            "spia_saa",
            "term_saa",
            "FIA",
            "SPIA",
            "WL",
            "Term",
            "get_credit_spreads",
            "get_spread",
            "get_treasury_rates",
            "read_credit_spread_indices",
            "update_credit_spreads",
        ],
    )
    def test_public_api_exported(self, symbol: str):
        assert hasattr(alm, symbol), f"alm.{symbol} not exported"
