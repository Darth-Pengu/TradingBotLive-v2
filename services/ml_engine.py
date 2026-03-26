"""
ZMN Bot ML Scoring Engine
===========================
CatBoost + LightGBM ensemble with auto_class_weights="Balanced".
- Retrain weekly on 7-day sliding window
- Min 50 samples before first train, 200 before production scoring
- 26 features (highest weight: liquidity_velocity, bonding_curve_progress, buy_sell_ratio_5min)
- Publishes ML scores to Redis for signal_aggregator consumption
- Listens on Redis for scoring requests and training triggers
"""

import asyncio
import json
import logging
import os
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import redis.asyncio as aioredis
from dotenv import load_dotenv

from services.db import get_pool

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ml_engine")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# --- ML thresholds per personality (Section 12) ---
ML_THRESHOLDS = {
    "speed_demon": 65,
    "analyst": 70,
    "whale_tracker": 70,
}

# Mode adjustments
ML_THRESHOLD_ADJUSTMENTS = {
    "FRENZY": -5,
    "DEFENSIVE": 10,
}

MIN_SAMPLES_FIRST_TRAIN = 50
MIN_SAMPLES_PRODUCTION = 200
RETRAIN_INTERVAL_SECONDS = 7 * 24 * 3600  # Weekly

# --- Feature definitions (26 features) ---
FEATURE_COLUMNS = [
    "liquidity_sol",
    "liquidity_velocity",          # 2x weight
    "bonding_curve_progress",      # 2x weight
    "buy_sell_ratio_5min",         # 2x weight
    "holder_count",
    "top10_holder_pct",
    "unique_buyers_30min",
    "volume_acceleration_15min",
    "dev_wallet_hold_pct",         # strong negative predictor
    "bundle_detected",             # strong negative predictor (0/1)
    "bundled_supply_pct",
    "bot_transaction_ratio",
    "fresh_wallet_ratio",
    "creator_prev_tokens_count",   # from signal_aggregator via Helius
    "creator_rug_count",           # from signal_aggregator via Rugcheck
    "creator_graduation_rate",     # from signal_aggregator
    "dev_sold_pct",                # from Helius enhanced dev sell check
    "token_age_seconds",
    "market_cap_usd",
    "volume_24h_usd",
    "price_change_5min_pct",
    "price_change_1h_pct",
    "sol_price_usd",
    "cfgi_score",
    "market_mode_encoded",         # HIBERNATE=0, DEFENSIVE=1, NORMAL=2, AGGRESSIVE=3, FRENZY=4
    "hour_of_day",
    "is_weekend",
    "signal_source_count",
    "whale_wallet_count",
]

# Weights for feature importance boosting (applied during training)
FEATURE_WEIGHTS = {
    "liquidity_velocity": 2.0,
    "bonding_curve_progress": 2.0,
    "buy_sell_ratio_5min": 2.0,
    "dev_wallet_hold_pct": 2.0,
    "dev_sold_pct": 2.0,
    "bundle_detected": 2.0,
    "creator_rug_count": 1.5,
}

MARKET_MODE_ENCODING = {
    "HIBERNATE": 0,
    "DEFENSIVE": 1,
    "NORMAL": 2,
    "AGGRESSIVE": 3,
    "FRENZY": 4,
}


class MLModel:
    """CatBoost + LightGBM ensemble."""

    def __init__(self):
        self.catboost_model = None
        self.lgbm_model = None
        self.is_trained = False
        self.sample_count = 0
        self.last_train_time = 0.0
        self._load_models()

    def _load_models(self):
        cb_path = MODEL_DIR / "catboost_model.pkl"
        lgbm_path = MODEL_DIR / "lgbm_model.pkl"
        meta_path = MODEL_DIR / "model_meta.json"

        if cb_path.exists() and lgbm_path.exists():
            try:
                with open(cb_path, "rb") as f:
                    self.catboost_model = pickle.load(f)
                with open(lgbm_path, "rb") as f:
                    self.lgbm_model = pickle.load(f)
                if meta_path.exists():
                    with open(meta_path, "r") as f:
                        meta = json.load(f)
                        self.sample_count = meta.get("sample_count", 0)
                        self.last_train_time = meta.get("last_train_time", 0)
                self.is_trained = True
                logger.info("Loaded existing models (samples=%d)", self.sample_count)
            except Exception as e:
                logger.warning("Failed to load models: %s — will retrain", e)
                self.is_trained = False

    def _save_models(self):
        try:
            with open(MODEL_DIR / "catboost_model.pkl", "wb") as f:
                pickle.dump(self.catboost_model, f)
            with open(MODEL_DIR / "lgbm_model.pkl", "wb") as f:
                pickle.dump(self.lgbm_model, f)
            with open(MODEL_DIR / "model_meta.json", "w") as f:
                json.dump({
                    "sample_count": self.sample_count,
                    "last_train_time": self.last_train_time,
                    "features": FEATURE_COLUMNS,
                }, f)
            logger.info("Models saved to %s", MODEL_DIR)
        except Exception as e:
            logger.error("Failed to save models: %s", e)

    async def train(self, pool):
        """Train on 7-day sliding window of trade outcomes."""
        try:
            from catboost import CatBoostClassifier
            from lightgbm import LGBMClassifier
        except ImportError as e:
            logger.error("ML library not installed: %s", e)
            return

        # Fetch training data from trades table
        seven_days_ago = datetime.now(timezone.utc).timestamp() - (7 * 86400)
        try:
            rows = await pool.fetch(
                """SELECT features_json, outcome FROM trades
                   WHERE created_at > $1 AND features_json IS NOT NULL AND outcome IS NOT NULL""",
                seven_days_ago,
            )
        except Exception as e:
            logger.warning("Could not fetch training data: %s", e)
            return

        if len(rows) < MIN_SAMPLES_FIRST_TRAIN:
            logger.info("Only %d samples (need %d) — skipping training", len(rows), MIN_SAMPLES_FIRST_TRAIN)
            return

        # Build DataFrame
        features_list = []
        labels = []
        for row in rows:
            features_json = row["features_json"]
            outcome = row["outcome"]
            try:
                features = json.loads(features_json)
                row = [features.get(col, 0) for col in FEATURE_COLUMNS]
                features_list.append(row)
                labels.append(1 if outcome == "profit" else 0)
            except (json.JSONDecodeError, TypeError):
                continue

        if len(features_list) < MIN_SAMPLES_FIRST_TRAIN:
            return

        X = pd.DataFrame(features_list, columns=FEATURE_COLUMNS)
        y = np.array(labels)

        # Apply feature weights via sample weighting
        sample_weights = np.ones(len(X))

        logger.info("Training on %d samples (%.1f%% positive)", len(X), y.mean() * 100)

        # CatBoost
        try:
            self.catboost_model = CatBoostClassifier(
                iterations=500,
                depth=6,
                learning_rate=0.05,
                auto_class_weights="Balanced",
                verbose=0,
                random_seed=42,
            )
            self.catboost_model.fit(X, y, sample_weight=sample_weights)
        except Exception as e:
            logger.error("CatBoost training failed: %s", e)
            return

        # LightGBM
        try:
            self.lgbm_model = LGBMClassifier(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.05,
                class_weight="balanced",
                random_state=42,
                verbose=-1,
            )
            self.lgbm_model.fit(X, y, sample_weight=sample_weights)
        except Exception as e:
            logger.error("LightGBM training failed: %s", e)
            return

        self.is_trained = True
        self.sample_count = len(X)
        self.last_train_time = time.time()
        self._save_models()
        logger.info("Training complete — CatBoost + LightGBM ensemble ready")

    def predict(self, features: dict) -> float:
        """
        Predict probability of profitable trade (0-100 score).
        Returns 50.0 (neutral) if model not trained.
        """
        if not self.is_trained:
            # Before model is trained, return neutral score
            # This lets the system operate in "pass-through" mode during initial data collection
            return 50.0

        try:
            row = [features.get(col, 0) for col in FEATURE_COLUMNS]
            X = pd.DataFrame([row], columns=FEATURE_COLUMNS)

            cb_proba = self.catboost_model.predict_proba(X)[0][1]
            lgbm_proba = self.lgbm_model.predict_proba(X)[0][1]

            # Ensemble: equal weight average
            ensemble_proba = (cb_proba + lgbm_proba) / 2.0
            return round(ensemble_proba * 100, 1)
        except Exception as e:
            logger.error("Prediction error: %s", e)
            return 50.0

    def passes_threshold(self, score: float, personality: str, market_mode: str = "NORMAL") -> bool:
        """Check if ML score passes the threshold for a personality."""
        base = ML_THRESHOLDS.get(personality, 70)
        adjustment = ML_THRESHOLD_ADJUSTMENTS.get(market_mode, 0)
        threshold = base + adjustment
        return score >= threshold


# --- Redis listener for scoring requests ---
async def _scoring_listener(model: MLModel, redis_conn: aioredis.Redis | None):
    """Listen for scoring requests on Redis and respond with ML scores."""
    if not redis_conn:
        logger.info("No Redis — scoring listener disabled")
        return

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("ml:score_request")
    logger.info("Listening for ML score requests on ml:score_request")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            request_id = data.get("request_id", "unknown")
            features = data.get("features", {})

            score = model.predict(features)
            response = {
                "request_id": request_id,
                "ml_score": score,
                "model_trained": model.is_trained,
                "sample_count": model.sample_count,
            }
            await redis_conn.publish("ml:score_response", json.dumps(response))
        except Exception as e:
            logger.error("Scoring request error: %s", e)


# --- Weekly retrain loop ---
async def _retrain_loop(model: MLModel):
    """Retrain model weekly."""
    pool = await get_pool()
    while True:
        elapsed = time.time() - model.last_train_time
        if elapsed >= RETRAIN_INTERVAL_SECONDS:
            logger.info("Weekly retrain triggered")
            try:
                await model.train(pool)
            except Exception as e:
                logger.error("Retrain failed: %s", e)
        # Check every hour
        await asyncio.sleep(3600)


# --- Main ---
async def main():
    logger.info("ML Engine starting (TEST_MODE=%s)", TEST_MODE)

    model = MLModel()

    # Initialize DB pool + attempt initial training
    pool = await get_pool()
    await model.train(pool)

    # Connect Redis always — ML scoring is read-only, needed for paper trading too
    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_conn.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s -- scoring disabled", e)

    await asyncio.gather(
        _scoring_listener(model, redis_conn),
        _retrain_loop(model),
    )


if __name__ == "__main__":
    asyncio.run(main())
