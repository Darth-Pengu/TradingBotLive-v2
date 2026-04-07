"""
MemeTrans dataset loader — 41,470 labeled pump.fun tokens, 131 features.
Downloads from GitHub and maps to ZMN Bot's 25-feature schema.

MemeTrans columns are grouped:
  group1: price/timing features
  group2: early holder distribution (at bonding curve)
  group3: transaction activity features
  group4: post-graduation holder distribution
  label: high/medium/low risk
  return_ratio: actual price return
"""

import logging
import subprocess
from pathlib import Path

import pandas as pd

logger = logging.getLogger("memetrans_loader")

MEMETRANS_REPO = "https://github.com/git-disl/MemeTrans.git"


def download_memetrans(target_dir="data/memetrans") -> Path:
    """Clone MemeTrans repo if not already present."""
    target = Path(target_dir)
    if not target.exists():
        logger.info("Cloning MemeTrans dataset to %s...", target)
        subprocess.run(["git", "clone", "--depth", "1", MEMETRANS_REPO, str(target)], check=True)
        logger.info("MemeTrans cloned successfully")
    else:
        logger.info("MemeTrans already present at %s", target)
    return target


def map_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map MemeTrans 131 features -> ZMN Bot 54-feature schema.
    Uses verified column names from the actual dataset.
    group2 = early (bonding curve) holder data
    group3 = transaction activity features
    group4 = post-graduation holder distribution
    """
    from services.ml_engine import FEATURE_COLUMNS

    mapped = pd.DataFrame(index=df.index)

    # --- Direct mappings from MemeTrans -> ZMN schema ---
    mapped["top10_holder_pct"] = df.get("group2_top10_pct", pd.Series(-1, index=df.index)) * 100
    mapped["dev_wallet_hold_pct"] = df.get("group2_dev_hold_pct", pd.Series(-1, index=df.index)) * 100
    mapped["fresh_wallet_ratio"] = df.get("group2_sniper_0s_ratio", pd.Series(-1, index=df.index))
    mapped["holder_count"] = df.get("group3_holder_num", pd.Series(-1, index=df.index))

    # Transaction-derived features
    buy_num = df.get("group3_buy_num", pd.Series(0, index=df.index))
    sell_num = df.get("group3_sell_num", pd.Series(1, index=df.index))
    mapped["buy_sell_ratio_5min"] = (buy_num / sell_num.replace(0, 1)).clip(0, 10)

    mapped["market_cap_usd"] = df.get("group3_buy_vol", pd.Series(0, index=df.index))
    mapped["token_age_seconds"] = df.get("group3_time_span", pd.Series(0, index=df.index))
    mapped["bot_transaction_ratio"] = df.get("group3_wash_ratio", pd.Series(0, index=df.index))
    mapped["bundled_supply_pct"] = df.get("group2_sniper_0s_hold_pct", pd.Series(0, index=df.index)) * 100

    # Bonding curve progress: if group1_price exists and is > 0, token graduated
    mapped["bonding_curve_progress"] = (df.get("group1_price", pd.Series(0, index=df.index)) > 0).astype(float)

    # Liquidity: use buy volume as proxy for SOL liquidity
    mapped["liquidity_sol"] = df.get("group3_buy_vol", pd.Series(0, index=df.index)) / 1e9

    # Sniper/bundle detection
    sniper_ratio = df.get("group2_sniper_0s_ratio", pd.Series(0, index=df.index))
    mapped["bundle_detected"] = (sniper_ratio > 0.1).astype(int)

    # Creator features — derive from dev hold patterns
    dev_hold = df.get("group2_dev_hold_ratio", pd.Series(1, index=df.index))
    mapped["creator_rug_rate"] = (1 - dev_hold).clip(0, 1)
    mapped["creator_rug_count"] = (mapped["creator_rug_rate"] > 0.5).astype(int)

    # --- NEW: 13 MemeTrans-derived features ---
    mapped["holder_gini"] = df.get("group2_holder_gini", pd.Series(-1, index=df.index))
    mapped["sniper_0s_num"] = df.get("group2_sniper_0s_num", pd.Series(-1, index=df.index))
    mapped["sniper_0s_hold_pct"] = df.get("group2_sniper_0s_hold_pct", pd.Series(-1, index=df.index))
    mapped["sniper_5s_ratio"] = df.get("group2_sniper_5s_ratio", pd.Series(-1, index=df.index))
    mapped["early_top5_hold_ratio"] = df.get("group2_early_top5_hold_ratio", pd.Series(-1, index=df.index))
    mapped["early_top10_realized_pnl_mean"] = df.get(
        "group2_early_top10_realized_pnl_mean", pd.Series(-1, index=df.index)
    )
    mapped["wash_ratio"] = df.get("group3_wash_ratio", pd.Series(-1, index=df.index))
    mapped["tx_per_sec"] = df.get("group3_tx_per_sec", pd.Series(-1, index=df.index))
    sell_vol = df.get("group3_sell_vol", pd.Series(0, index=df.index))
    total_vol = df.get("group3_buy_vol", pd.Series(0, index=df.index)) + sell_vol
    mapped["sell_pressure"] = (sell_vol / total_vol.replace(0, 1)).clip(0, 1)
    mapped["post_grad_holder_gini"] = df.get("group4_holder_gini", pd.Series(-1, index=df.index))
    mapped["cluster_num"] = df.get("group4_cluster_num", pd.Series(-1, index=df.index))
    mapped["cluster_holder_ratio"] = df.get("group4_cluster_holder_ratio", pd.Series(-1, index=df.index))
    # top10 concentration change: group4 minus group2
    g4_top10 = df.get("group4_top10_pct", pd.Series(0, index=df.index))
    g2_top10 = df.get("group2_top10_pct", pd.Series(0, index=df.index))
    mapped["top10_pct_delta"] = g4_top10 - g2_top10

    # Features with no MemeTrans equivalent — fill with -1 sentinel
    for col in FEATURE_COLUMNS:
        if col not in mapped.columns:
            mapped[col] = -1

    # Reorder to match schema
    mapped = mapped[FEATURE_COLUMNS]

    matched = sum(1 for col in FEATURE_COLUMNS if not (mapped[col] == -1).all())
    logger.info("Mapped %d/%d features from MemeTrans (%d rows)", matched, len(FEATURE_COLUMNS), len(df))
    return mapped


def construct_outcome_labels(df: pd.DataFrame) -> pd.Series:
    """
    Construct win/loss labels from MemeTrans data.
    MemeTrans labels: high=rug/loss, medium=breakeven, low=win
    return_ratio: actual price return (negative = loss)
    """
    if "label" in df.columns:
        labels = df["label"].map({
            "high": "loss",
            "medium": "loss",  # medium risk = still a loss for our purposes
            "low": "win",
        })
        logger.info("Labels from MemeTrans risk_level: %s", labels.value_counts().to_dict())
        return labels

    if "return_ratio" in df.columns:
        labels = pd.Series("loss", index=df.index)
        labels[df["return_ratio"] > 0] = "win"
        logger.info("Labels from return_ratio: %s", labels.value_counts().to_dict())
        return labels

    logger.warning("No label column found")
    return pd.Series("loss", index=df.index)


def load_memetrans(target_dir="data/memetrans") -> tuple[pd.DataFrame, pd.Series] | None:
    """Full pipeline: download, load, map, label."""
    repo = download_memetrans(target_dir)
    main_file = repo / "dataset" / "feat_label.csv"

    if not main_file.exists():
        # Fallback: find largest CSV
        files = sorted(repo.rglob("*.csv"), key=lambda f: f.stat().st_size, reverse=True)
        if not files:
            logger.error("No CSV files found in MemeTrans repo")
            return None
        main_file = files[0]

    logger.info("Loading %s...", main_file.name)
    df = pd.read_csv(main_file)
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    X = map_features(df)
    y = construct_outcome_labels(df)
    return X, y
