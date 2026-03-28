"""
MemeTrans dataset loader — 41,470 labeled pump.fun tokens, 122 features.
Downloads from GitHub and maps to ZMN Bot's 25-feature schema.
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


def find_data_files(repo_dir: Path) -> list[Path]:
    """Find CSV/parquet files in the MemeTrans repo."""
    files = list(repo_dir.rglob("*.csv")) + list(repo_dir.rglob("*.parquet"))
    # Sort by size descending — largest file is likely the main dataset
    files.sort(key=lambda f: f.stat().st_size, reverse=True)
    return files


def map_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map MemeTrans features -> ZMN Bot 25-feature schema.
    Column names are matched best-effort; inspect actual columns first.
    """
    from services.ml_model_accelerator import FEATURE_SCHEMA

    mapped = pd.DataFrame(index=df.index)
    actual_cols = set(df.columns)

    # Mapping: ZMN feature -> list of candidate MemeTrans column names
    candidates = {
        "liquidity_sol": ["sol_raised", "total_sol", "bonding_curve_sol", "liquidity_sol"],
        "buy_sell_ratio_5min": ["buy_count_5min", "trade_ratio_early", "buy_sell_ratio_5min", "buy_sell_ratio"],
        "bonding_curve_progress": ["bonding_progress", "curve_completion_pct", "bonding_curve_progress"],
        "holder_count": ["unique_buyers", "holder_count", "num_unique_wallets"],
        "top10_holder_pct": ["top10_concentration", "hhi_index", "top10_holder_pct"],
        "dev_wallet_hold_pct": ["creator_holding_pct", "deployer_balance_pct", "dev_wallet_hold_pct"],
        "bundle_detected": ["has_bundle", "jito_bundle_detected", "bundle_ratio", "bundle_detected"],
        "fresh_wallet_ratio": ["new_wallet_pct", "fresh_wallet_ratio"],
        "creator_prev_launches": ["creator_token_count", "deployer_history_count", "creator_prev_launches"],
        "creator_rug_rate": ["creator_fail_rate", "deployer_rug_rate", "creator_rug_rate"],
        "token_age_seconds": ["age_at_snapshot", "time_since_creation", "token_age_seconds"],
        "market_cap_usd": ["market_cap", "mcap_usd", "market_cap_usd"],
        "mint_authority_revoked": ["mint_authority_revoked"],
        "cfgi_score": ["cfgi_score"],
        "sol_price_usd": ["sol_price_usd", "sol_price"],
        "nansen_sm_count": ["nansen_sm_count"],
        "liquidity_velocity": ["liquidity_velocity"],
        "unique_buyers_30min": ["unique_buyers_30min"],
        "volume_acceleration_15min": ["volume_acceleration_15min"],
        "dev_sold_pct": ["dev_sold_pct"],
        "bot_transaction_ratio": ["bot_transaction_ratio"],
        "bundled_supply_pct": ["bundled_supply_pct"],
        "creator_rug_count": ["creator_rug_count"],
        "nansen_sm_inflow_ratio": ["nansen_sm_inflow_ratio"],
        "nansen_concentration_risk": ["nansen_concentration_risk"],
    }

    matched = 0
    for zmn_col, candidate_names in candidates.items():
        found = False
        for cand in candidate_names:
            if cand in actual_cols:
                mapped[zmn_col] = df[cand]
                found = True
                matched += 1
                break
        if not found:
            mapped[zmn_col] = -1  # Sentinel for missing features

    logger.info("Mapped %d/%d features from MemeTrans (%d columns in source)",
                matched, len(FEATURE_SCHEMA), len(actual_cols))

    # Log which features are missing
    missing = [col for col in FEATURE_SCHEMA if col not in mapped.columns or (mapped[col] == -1).all()]
    if missing:
        logger.info("Missing features (filled with -1): %s", missing)

    return mapped


def construct_outcome_labels(df: pd.DataFrame) -> pd.Series | None:
    """
    Construct win/loss labels from MemeTrans data.
    Uses risk_level annotations if available, else reconstructs from price data.
    """
    if "risk_level" in df.columns:
        labels = df["risk_level"].map({
            "high_risk": "loss",
            "medium_risk": "breakeven",
            "low_risk": "win",
        })
        logger.info("Labels from risk_level: %s", labels.value_counts().to_dict())
        return labels

    if "peak_price_ratio" in df.columns:
        labels = pd.Series("loss", index=df.index)
        labels[df["peak_price_ratio"] >= 2.0] = "win"
        labels[(df["peak_price_ratio"] >= 0.8) & (df["peak_price_ratio"] < 2.0)] = "breakeven"
        logger.info("Labels from peak_price_ratio: %s", labels.value_counts().to_dict())
        return labels

    # Try label column directly
    if "label" in df.columns:
        logger.info("Labels from 'label' column: %s", df["label"].value_counts().to_dict())
        return df["label"].map(lambda v: "win" if v == 1 or v == "win" else "loss")

    logger.warning("No label column found in MemeTrans data")
    return None


def load_memetrans(target_dir="data/memetrans") -> tuple[pd.DataFrame, pd.Series] | None:
    """Full pipeline: download, load, map, label."""
    repo = download_memetrans(target_dir)
    files = find_data_files(repo)
    if not files:
        logger.error("No data files found in MemeTrans repo")
        return None

    logger.info("Found %d data files: %s", len(files), [f.name for f in files[:5]])
    main_file = files[0]

    if main_file.suffix == ".parquet":
        df = pd.read_parquet(main_file)
    else:
        df = pd.read_csv(main_file)

    logger.info("Loaded %d rows, %d columns from %s", len(df), len(df.columns), main_file.name)
    logger.info("Columns: %s", df.columns.tolist()[:30])

    X = map_features(df)
    y = construct_outcome_labels(df)
    if y is None:
        return None

    return X, y
