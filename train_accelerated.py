"""
Main training script for accelerated ML engine.
Usage: python train_accelerated.py --data-source [bootstrap|memetrans|combined]
"""

import argparse
import logging
import sys

import pandas as pd

from services.ml_model_accelerator import AcceleratedMLEngine, FEATURE_SCHEMA
from services.memetrans_loader import load_memetrans

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("train_accelerated")


def load_bootstrap_data(path="data/training_samples.csv"):
    """Load locally collected training samples."""
    df = pd.read_csv(path)
    available = [c for c in FEATURE_SCHEMA if c in df.columns]
    logger.info("Bootstrap data: %d rows, %d/%d features available", len(df), len(available), len(FEATURE_SCHEMA))
    X = df[available].copy()
    # Add missing features as -1
    for col in FEATURE_SCHEMA:
        if col not in X.columns:
            X[col] = -1
    y = df["outcome"]
    return X, y


def main():
    parser = argparse.ArgumentParser(description="Train ZMN Bot accelerated ML model")
    parser.add_argument("--data-source", choices=["bootstrap", "memetrans", "combined"], default="combined")
    parser.add_argument("--binary", action="store_true", default=True, help="Binary classification (win vs not-win)")
    parser.add_argument("--model-dir", default="data/models", help="Model output directory")
    args = parser.parse_args()

    engine = AcceleratedMLEngine(model_dir=args.model_dir, use_binary=args.binary)

    X_parts = []
    y_parts = []

    if args.data_source in ("bootstrap", "combined"):
        try:
            X_boot, y_boot = load_bootstrap_data()
            X_parts.append(X_boot)
            y_parts.append(y_boot)
            logger.info("Bootstrap data loaded: %d samples", len(X_boot))
        except FileNotFoundError:
            logger.warning("No bootstrap data at data/training_samples.csv — skipping")

    if args.data_source in ("memetrans", "combined"):
        result = load_memetrans()
        if result is not None:
            X_meme, y_meme = result
            X_parts.append(X_meme)
            y_parts.append(y_meme)
            logger.info("MemeTrans data loaded: %d samples", len(X_meme))
        else:
            logger.warning("MemeTrans data not available — skipping")

    if not X_parts:
        logger.error("No training data available from any source")
        sys.exit(1)

    X = pd.concat(X_parts, ignore_index=True)
    y = pd.concat(y_parts, ignore_index=True)
    logger.info("Total training data: %d samples", len(X))

    results = engine.train_from_dataframe(X, y)
    print(f"\nTraining complete: {results}")

    # --- Validation criteria for live trading ---
    print("\n=== LIVE TRADING READINESS CHECK ===")
    ready = True

    if results["n_samples"] < 500:
        print(f"  FAIL  Need 500+ samples, have {results['n_samples']}")
        ready = False
    else:
        print(f"  PASS  Sample count: {results['n_samples']}")

    if results["cv_auc_mean"] < 0.60:
        print(f"  FAIL  CV AUC {results['cv_auc_mean']:.4f} below 0.60 threshold")
        ready = False
    else:
        print(f"  PASS  CV AUC: {results['cv_auc_mean']:.4f}")

    lower_bound = results["cv_auc_mean"] - results["cv_auc_std"]
    if lower_bound < 0.55:
        print(f"  FAIL  Lower bound AUC {lower_bound:.4f} below 0.55")
        ready = False
    else:
        print(f"  PASS  AUC lower bound: {lower_bound:.4f}")

    if results["phase"] < 2:
        print(f"  FAIL  Phase {results['phase']} — need Phase 2+ (TabPFN + CatBoost)")
        ready = False
    else:
        print(f"  PASS  Phase: {results['phase']}")

    if ready:
        print("\n  MODEL READY FOR LIVE TRADING")
        print("  Switch ML_ENGINE=accelerated in Railway env vars")
    else:
        print("\n  MODEL NOT READY — continue paper trading and collecting samples")

    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
