"""Tests for alm.core.Block class."""

import polars as pl
import pytest

from alm.core import Block, default_saa, spia_saa
from alm.liability import FIA, SPIA, Term

from .conftest import make_mortality as _make_mortality


class TestBlock:
    """Core Block tests using Term liability."""

    @pytest.fixture()
    def block(self) -> Block:
        return Block(
            liability_type="Term",
            saa=default_saa(),
            total_liability_amount=10_000_000,
            mortality_table=_make_mortality(),
            age_range=(35, 55),
            discount_rate=0.04,
            n_policies=50,
            seed=42,
        )

    def test_invalid_liability_type(self):
        with pytest.raises(ValueError, match="liability_type"):
            Block(
                liability_type="Invalid",
                saa=default_saa(),
                total_liability_amount=1_000,
                mortality_table=_make_mortality(),
                age_range=(30, 50),
                discount_rate=0.04,
            )

    def test_generate_policies_count(self, block: Block):
        policies = block.generate_policies()
        assert len(policies) == 50

    def test_generate_policies_type(self, block: Block):
        policies = block.generate_policies()
        assert all(isinstance(p, Term) for p in policies)

    def test_generate_assets_nonempty(self, block: Block):
        assets = block.generate_assets()
        assert len(assets) > 0

    def test_liability_cashflows_returns_df(self, block: Block):
        block.generate_policies()
        cf = block.liability_cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert "year" in cf.columns
        assert "cashflow" in cf.columns

    def test_asset_cashflows_returns_df(self, block: Block):
        block.generate_assets()
        cf = block.asset_cashflows()
        assert isinstance(cf, pl.DataFrame)
        assert "year" in cf.columns
        assert "cashflow" in cf.columns

    def test_plot_cashflows_returns_figure(self, block: Block):
        block.generate_policies()
        block.generate_assets()
        fig = block.plot_cashflows()
        assert fig is not None

    def test_government_bonds_carry_no_spread(self, block: Block):
        """Treasuries are the risk-free benchmark: coupon equals the block rate, spread is zero."""
        from alm.asset import Bond

        govt = [a for a in block.generate_assets() if isinstance(a, Bond) and a.rating == "AA+"]
        assert govt, "block should hold government bonds"
        assert all(b.credit_spread == 0.0 for b in govt)
        assert all(b.coupon_rate == pytest.approx(block.discount_rate) for b in govt)

    def test_corporate_bonds_carry_spread(self, block: Block):
        from alm.asset import Bond

        corp = [a for a in block.generate_assets() if isinstance(a, Bond) and a.rating != "AA+"]
        assert corp
        assert all(b.credit_spread > 0.0 for b in corp)

    def test_wl_and_term_policies_are_single_premium_equivalent(self, block: Block):
        policies = block.generate_policies()
        assert all(p.annual_premium == 0.0 for p in policies)

    def test_seed_reproducibility(self, block: Block):
        policies_1 = block.generate_policies()
        ages_1 = [p.age for p in policies_1]
        # Reset by creating new block with same seed
        block2 = Block(
            liability_type="Term",
            saa=default_saa(),
            total_liability_amount=10_000_000,
            mortality_table=_make_mortality(),
            age_range=(35, 55),
            discount_rate=0.04,
            n_policies=50,
            seed=42,
        )
        policies_2 = block2.generate_policies()
        ages_2 = [p.age for p in policies_2]
        assert ages_1 == ages_2


class TestBlockPremium:
    """Tests for premium calculation and investable amount logic."""

    def test_calculate_premium_wl_less_than_face(self):
        """For WL, calculated premium should be much less than face value."""
        block = Block(
            liability_type="WL",
            saa=default_saa(),
            total_liability_amount=1_000_000,
            mortality_table=_make_mortality(),
            age_range=(35, 55),
            discount_rate=0.04,
            n_policies=10,
            seed=42,
        )
        premium = block.calculate_premium()
        assert premium > 0
        assert premium < block.total_liability_amount

    def test_calculate_premium_term_less_than_face(self):
        """For Term, calculated premium should be much less than face value."""
        block = Block(
            liability_type="Term",
            saa=default_saa(),
            total_liability_amount=10_000_000,
            mortality_table=_make_mortality(),
            age_range=(35, 55),
            discount_rate=0.04,
            n_policies=50,
            seed=42,
        )
        premium = block.calculate_premium()
        assert premium > 0
        assert premium < block.total_liability_amount

    def test_premium_includes_loading(self):
        """A higher loading on the net single premium produces a higher premium."""
        kwargs = dict(
            liability_type="WL",
            saa=default_saa(),
            total_liability_amount=1_000_000,
            mortality_table=_make_mortality(),
            age_range=(40, 50),
            discount_rate=0.04,
            n_policies=10,
            seed=42,
        )
        block_low = Block(**kwargs, premium_loading=0.02)
        block_high = Block(**kwargs, premium_loading=0.10)
        assert block_high.calculate_premium() > block_low.calculate_premium()

    def test_explicit_premium_used_for_assets(self):
        """When premium is provided, generate_assets uses it directly."""
        block = Block(
            liability_type="WL",
            saa=default_saa(),
            total_liability_amount=1_000_000,
            mortality_table=_make_mortality(),
            age_range=(40, 50),
            discount_rate=0.04,
            n_policies=10,
            premium=200_000,
            seed=42,
        )
        assets = block.generate_assets()
        total_invested = sum(
            getattr(a, "face_value", 0) or getattr(a, "principal", 0) for a in assets
        )
        assert abs(total_invested - 200_000) < 1.0

    def test_auto_premium_when_none(self):
        """generate_assets auto-calculates premium when not provided."""
        block = Block(
            liability_type="WL",
            saa=default_saa(),
            total_liability_amount=1_000_000,
            mortality_table=_make_mortality(),
            age_range=(40, 50),
            discount_rate=0.04,
            n_policies=10,
            seed=42,
        )
        assert block.premium is None
        block.generate_assets()
        assert block.premium is not None
        assert block.premium < block.total_liability_amount


class TestBlockSPIA:
    """Test Block with SPIA liability type."""

    def test_spia_block_policies(self):
        block = Block(
            liability_type="SPIA",
            saa=spia_saa(),
            total_liability_amount=5_000_000,
            mortality_table=_make_mortality(min_age=60),
            age_range=(65, 80),
            discount_rate=0.04,
            n_policies=20,
            seed=123,
        )
        policies = block.generate_policies()
        assert all(isinstance(p, SPIA) for p in policies)
        assert len(policies) == 20


class TestBlockFIA:
    """Test Block with FIA liability type."""

    def test_fia_block_policies(self):
        block = Block(
            liability_type="FIA",
            saa=default_saa(),
            total_liability_amount=1_000_000,
            mortality_table=_make_mortality(min_age=50),
            age_range=(50, 60),
            discount_rate=0.04,
            n_policies=10,
            index_returns=[0.04] * 15,
            seed=99,
        )
        policies = block.generate_policies()
        assert all(isinstance(p, FIA) for p in policies)
        cf = block.liability_cashflows()
        assert isinstance(cf, pl.DataFrame)

    def test_fia_block_requires_index_returns(self):
        with pytest.raises(ValueError, match="index_returns"):
            Block(
                liability_type="FIA",
                saa=default_saa(),
                total_liability_amount=1_000_000,
                mortality_table=_make_mortality(min_age=50),
                age_range=(50, 60),
                discount_rate=0.04,
                n_policies=10,
                seed=99,
            )
