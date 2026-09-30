"""Tests for alm.examples: the shared lecture book and its two-swap hedge."""

import pytest

from alm.core import dollar_convexity, dv01
from alm.examples import asset_face, asset_yield, lecture_book


@pytest.fixture(scope="module")
def book():
    return lecture_book()


class TestLectureBook:
    def test_assets_are_at_par(self, book):
        """Each instrument is valued at its own yield, so the book equals the sum of par amounts."""
        sheet = book.balance_sheet()
        assert sheet["assets"] == pytest.approx(sum(asset_face(a) for a in book.assets), rel=1e-9)
        assert sheet["assets"] == pytest.approx(50_000_000)

    def test_balance_sheet_balances(self, book):
        sheet = book.balance_sheet()
        assert sheet["liabilities"] == pytest.approx(
            sheet["whole_life"] + sheet["spia"] + sheet["fia"]
        )
        assert sheet["surplus"] == pytest.approx(sheet["assets"] - sheet["liabilities"])
        assert sheet["whole_life"] == 0.0  # net level premium: zero reserve at issue
        assert sum(book.assets_by_class().values()) == pytest.approx(sheet["assets"])

    def test_treasuries_yield_the_risk_free_rate(self, book):
        for asset, rating in zip(book.assets, book.ratings, strict=True):
            if rating == "AA+":
                assert asset_yield(asset) == pytest.approx(book.discount_rate)
            else:
                assert asset_yield(asset) > book.discount_rate

    def test_surplus_falls_when_rates_fall(self, book):
        """Liabilities are longer than assets, so a rate drop hurts the unhedged surplus."""
        assert book.surplus(0.03) < book.surplus(0.04) < book.surplus(0.05)


class TestTwoSwapHedge:
    def test_hedge_closes_both_gaps(self, book):
        hedge = book.two_swap_hedge()
        r = book.discount_rate

        def hedged_wl_spia_surplus(rate: float) -> float:
            return book.pv_assets(rate) + hedge.pv(rate) - book.pv_liab_hedged(rate)

        assert dv01(hedged_wl_spia_surplus, r) == pytest.approx(0.0, abs=1.0)
        assert dollar_convexity(hedged_wl_spia_surplus, r) == pytest.approx(0.0, abs=1e5)

    def test_hedge_stabilises_surplus(self, book):
        hedge = book.two_swap_hedge()
        unhedged = [book.surplus(0.04 + s) for s in (-0.01, 0.0, 0.01)]
        hedged = [book.surplus(0.04 + s, hedge) for s in (-0.01, 0.0, 0.01)]
        assert max(hedged) - min(hedged) < 0.2 * (max(unhedged) - min(unhedged))

    def test_positions_match_signed_notionals(self, book):
        hedge = book.two_swap_hedge()
        for notional, position, tenor in zip(
            hedge.notionals, hedge.positions, hedge.tenors, strict=True
        ):
            assert position.notional == pytest.approx(abs(notional))
            assert position.pay_fixed == (notional < 0)
            assert position.tenor == tenor
        assert hedge.gross_notional == pytest.approx(sum(abs(n) for n in hedge.notionals))
        assert hedge.pv(book.discount_rate) == pytest.approx(0.0, abs=1e-6)  # at-market swaps
