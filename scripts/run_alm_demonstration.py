"""ALM Block-level simulation demonstration.

Creates one Block per liability type (SPIA, WL, Term, FIA) with
100 policies each, generates matching assets per SAA, and prints
summary cashflow statistics.
"""

import logging
import random
import sys
from pathlib import Path

import coloredlogs
import polars as pl

from alm.core import Block, default_saa, irr, spia_saa, term_saa
from alm.read import get_2012_iam_table, update_credit_spreads

sys.stdout.reconfigure(encoding="utf-8")
coloredlogs.install(level="INFO", fmt="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ── Refresh Assumptions ───────────────────────────────────────────
update_credit_spreads()

# ── Parameters ────────────────────────────────────────────────────
DISCOUNT_RATE = 0.04
SEED = 42
N_POLICIES = 100

mortality = get_2012_iam_table()

# Simulated equity-index annual returns for FIA crediting
rng = random.Random(SEED)
INDEX_RATES = [rng.gauss(0.05, 0.10) for _ in range(20)]

# ── Block Definitions ─────────────────────────────────────────────
blocks = {
    "SPIA": Block(
        liability_type="SPIA",
        saa=spia_saa(),
        total_liability_amount=2_000_000_000,
        mortality_table=mortality,
        age_range=(65, 80),
        discount_rate=DISCOUNT_RATE,
        n_policies=N_POLICIES,
        seed=SEED,
    ),
    "WL": Block(
        liability_type="WL",
        saa=default_saa(),
        total_liability_amount=1_000_000_000,
        mortality_table=mortality,
        age_range=(30, 50),
        discount_rate=DISCOUNT_RATE,
        n_policies=N_POLICIES,
        seed=SEED,
    ),
    "Term": Block(
        liability_type="Term",
        saa=term_saa(),
        total_liability_amount=5_000_000_000,
        mortality_table=mortality,
        age_range=(35, 55),
        discount_rate=DISCOUNT_RATE,
        n_policies=N_POLICIES,
        seed=SEED,
    ),
    "FIA": Block(
        liability_type="FIA",
        saa=default_saa(),
        total_liability_amount=500_000_000,
        mortality_table=mortality,
        age_range=(50, 65),
        discount_rate=DISCOUNT_RATE,
        n_policies=N_POLICIES,
        seed=SEED,
        index_rates=INDEX_RATES,
    ),
}

# ── Run Simulation ────────────────────────────────────────────────
logger.info("ALM Block-Level Simulation")
logger.info("Discount rate: %s", f"{DISCOUNT_RATE:.1%}")
logger.info("Policies per block: %d", N_POLICIES)
logger.info("")

summary_rows: list[dict] = []
block_cf_tables: dict[str, pl.DataFrame] = {}

for name, block in blocks.items():
    logger.info("-- %s Block %s", name, "-" * (50 - len(name)))
    block.generate_policies()
    block.generate_assets()

    liab_cf = block.liability_cashflows()
    asset_cf = block.asset_cashflows()

    premium = block.premium
    max_year = max(liab_cf["year"].max(), asset_cf["year"].max())

    # PV: discount aggregated annual cashflows at the block rate
    pv_liab = sum(
        cf / (1 + DISCOUNT_RATE) ** yr
        for yr, cf in zip(liab_cf["year"], liab_cf["cashflow"], strict=True)
    )
    pv_asset = sum(
        cf / (1 + DISCOUNT_RATE) ** yr
        for yr, cf in zip(asset_cf["year"], asset_cf["cashflow"], strict=True)
    )

    # Asset IRR: initial outlay is the invested premium
    asset_cfs_by_year = asset_cf.sort("year")["cashflow"].to_list()
    asset_irr = irr([-premium] + asset_cfs_by_year)

    logger.info("  Policies:           %6s", f"{len(block._policies):,}")
    logger.info("  Assets:             %6s", f"{len(block._assets):,}")
    logger.info("  Premium:            $%18s", f"{premium:,.0f}")
    logger.info("  Horizon:            %6d years", max_year)
    logger.info("  PV liab:          $%18s", f"{pv_liab:,.0f}")
    logger.info("  PV asset:         $%18s", f"{pv_asset:,.0f}")
    logger.info("  PV Surplus (A - L): $%18s", f"{pv_asset - pv_liab:,.0f}")
    logger.info("  Asset IRR:          %18s", f"{asset_irr:.2%}")
    logger.info("")

    summary_rows.append(
        {
            "block": name,
            "policies": len(block._policies),
            "assets": len(block._assets),
            "premium": premium,
            "horizon": max_year,
            "pv_liab": pv_liab,
            "pv_asset": pv_asset,
            "pv_surplus": pv_asset - pv_liab,
            "profit_margin": pv_asset / pv_liab - 1,
            "asset_irr": asset_irr,
        }
    )

    # Build per-year CF table for this block
    combined = (
        asset_cf.rename({"cashflow": "assets"})
        .join(
            liab_cf.rename({"cashflow": "liabilities"}),
            on="year",
            how="full",
            coalesce=True,
        )
        .fill_null(0.0)
        .sort("year")
        .with_columns(
            (pl.col("assets") - pl.col("liabilities")).alias("surplus"),
            (1 / (1 + DISCOUNT_RATE) ** pl.col("year")).alias("pv_factor"),
        )
    )
    block_cf_tables[name] = combined


# ── Cashflow Detail by Year and Block ─────────────────────────────
for name, cf_table in block_cf_tables.items():
    logger.info("")
    logger.info("%s — Annual Cashflows", name)
    display = cf_table.with_columns(
        pl.col("assets").round(0).cast(pl.Int64),
        pl.col("liabilities").round(0).cast(pl.Int64),
        pl.col("surplus").round(0).cast(pl.Int64),
        pl.col("pv_factor").round(6),
    )
    with pl.Config(tbl_rows=100, thousands_separator=","):
        logger.info("\n%s", display)

# ── Summary Table ─────────────────────────────────────────────────
summary = pl.DataFrame(summary_rows)
logger.info("Summary")
logger.info("\n%s", summary)
