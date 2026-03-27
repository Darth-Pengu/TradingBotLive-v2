"""
ZMN Bot ML Scoring Engine
===========================
CatBoost + LightGBM + XGBoost ensemble with class balancing.
- Retrain weekly on 7-day sliding window
- Min 50 samples before first train, 200 before production scoring
- 37 features: 26 original + 11 Nansen (flow, quant scores, holder labels)
- Publishes ML scores to Redis for signal_aggregator consumption
- Listens on Redis for scoring requests and training triggers
- Backwards compatible: missing Nansen features default to 0
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
INCREMENTAL_UPDATE_INTERVAL = 50  # trades since last update

# --- Feature definitions (44 features: 26 original + 11 Nansen + 7 new) ---
FEATURE_COLUMNS = [
    # === Original 26 features ===
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
    # === Nansen flow features (P0 — token_recent_flows_summary) ===
    "nansen_sm_inflow_ratio",      # smart money flow / average (>1 = bullish)
    "nansen_whale_outflow_ratio",  # whale outflow / average (>1 = bearish)
    "nansen_exchange_flow",        # exchange net flow (positive = selling)
    "nansen_fresh_wallet_flow_ratio",  # fresh wallet activity / avg (>5 = suspicious)
    # === Nansen quant score features (P0 — token_quant_scores) ===
    "nansen_performance_score",    # -60 to +75 normalized to ~[-0.8, 1.0]
    "nansen_risk_score",           # -60 to +80 normalized
    "nansen_concentration_risk",   # 1=low, 0=medium, -1=high
    # === Nansen holder features (P1 — labeled top holders) ===
    "nansen_labeled_exchange_holder_pct",  # % held by exchange addresses
    # === 7 new features (Section 23 AGENT_CONTEXT.md) ===
    "creator_prev_launches",       # count of prior token launches by deployer
    "creator_rug_rate",            # fraction of prior launches that failed (<24h)
    "creator_avg_hold_hours",      # avg time creator held own tokens
    "jito_bundle_count",           # bundled txs in first 10 trades (0-10)
    "jito_tip_lamports",           # avg Jito tip in first bundles
    "token_freshness_score",       # exp(-age_hours / 6) decay function
    "mint_authority_revoked",      # 1=revoked, 0=active
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
    # Nansen features with elevated weights
    "nansen_sm_inflow_ratio": 1.5,
    "nansen_concentration_risk": 1.5,
    "nansen_fresh_wallet_flow_ratio": 1.5,
    # New features with elevated weights — strong rug/safety signals
    "creator_rug_rate": 2.0,           # deployer rug history is very predictive
    "jito_bundle_count": 1.5,          # bundle activity = coordinated manipulation
    "mint_authority_revoked": 1.5,     # unrevoked = rug vector
}

MARKET_MODE_ENCODING = {
    "HIBERNATE": 0,
    "DEFENSIVE": 1,
    "NORMAL": 2,
    "AGGRESSIVE": 3,
    "FRENZY": 4,
}


class DriftDetector:
    """
    ADWIN drift detector using River ML.
    Monitors rolling prediction error rate.
    When drift detected, triggers emergency model retrain.
    """

    def __init__(self):
        try:
            from river.drift import ADWIN
            self.detector = ADWIN(delta=0.002)
            self.available = True
            logger.info("ADWIN drift detection enabled (~1MB overhead)")
        except ImportError:
            self.detector = None
            self.available = False
            logger.warning("River ML not installed — drift detection disabled")
        self.drift_count = 0
        self.last_drift_time = 0.0

    def update(self, prediction: float, actual_outcome: int) -> bool:
        """
        Update with latest prediction error.
        Returns True if drift detected (trigger emergency retrain).
        prediction: ML score 0-100
        actual_outcome: 1=profit, 0=loss
        """
        if not self.available:
            return False
        # Error = 1 if prediction was wrong direction
        predicted_positive = prediction >= 65.0
        error = int(predicted_positive != bool(actual_outcome))
        self.detector.update(error)
        if self.detector.drift_detected:
            self.drift_count += 1
            self.last_drift_time = time.time()
            logger.warning(
                "ADWIN drift detected! (#%d) — "
                "market regime may have changed — triggering emergency retrain",
                self.drift_count,
            )
            return True
        return False


class MLModel:
    """CatBoost + LightGBM + XGBoost ensemble with drift detection."""

    def __init__(self):
        self.catboost_model = None
        self.lgbm_model = None
        self.xgb_model = None
        self.is_trained = False
        self.sample_count = 0
        self.last_train_time = 0.0
        self.last_update_time = 0.0
        self.trades_since_last_update = 0
        self.total_trades_trained = 0
        self.flaml_model = None
        self.best_flaml_config = None
        self.drift_detector = DriftDetector()
        self._load_models()

    def _load_models(self):
        cb_path = MODEL_DIR / "catboost_model.pkl"
        lgbm_path = MODEL_DIR / "lgbm_model.pkl"
        xgb_path = MODEL_DIR / "xgb_model.pkl"
        meta_path = MODEL_DIR / "model_meta.json"

        if cb_path.exists() and lgbm_path.exists() and xgb_path.exists():
            try:
                with open(cb_path, "rb") as f:
                    self.catboost_model = pickle.load(f)
                with open(lgbm_path, "rb") as f:
                    self.lgbm_model = pickle.load(f)
                with open(xgb_path, "rb") as f:
                    self.xgb_model = pickle.load(f)
                if meta_path.exists():
                    with open(meta_path, "r") as f:
                        meta = json.load(f)
                        self.sample_count = meta.get("sample_count", 0)
                        self.last_train_time = meta.get("last_train_time", 0)
                        self.last_update_time = meta.get("last_update_time", 0)
                        self.trades_since_last_update = meta.get("trades_since_last_update", 0)
                        self.total_trades_trained = meta.get("total_trades_trained", 0)
                self.is_trained = True
                logger.info("Loaded existing models (samples=%d)", self.sample_count)
                # Load optional FLAML model
                flaml_path = MODEL_DIR / "flaml_model.pkl"
                if flaml_path.exists():
                    try:
                        with open(flaml_path, "rb") as f:
                            self.flaml_model = pickle.load(f)
                        logger.info("FLAML model loaded (4th ensemble member)")
                    except Exception:
                        pass
            except Exception as e:
                logger.warning("Failed to load models: %s — will retrain", e)
                self.is_trained = False

    def _save_models(self):
        try:
            with open(MODEL_DIR / "catboost_model.pkl", "wb") as f:
                pickle.dump(self.catboost_model, f)
            with open(MODEL_DIR / "lgbm_model.pkl", "wb") as f:
                pickle.dump(self.lgbm_model, f)
            with open(MODEL_DIR / "xgb_model.pkl", "wb") as f:
                pickle.dump(self.xgb_model, f)
            meta = {
                "sample_count": self.sample_count,
                "last_train_time": self.last_train_time,
                "last_update_time": self.last_update_time,
                "trades_since_last_update": self.trades_since_last_update,
                "total_trades_trained": self.total_trades_trained,
                "features": FEATURE_COLUMNS,
                "feature_count": len(FEATURE_COLUMNS),
            }
            # Include SHAP feature importance if computed
            fi = getattr(self, "_feature_importance", {})
            if fi:
                meta["feature_importance"] = fi
                meta["top_5_features"] = list(fi.keys())[:5]
            # Preserve existing accuracy tracking if present
            meta_path = MODEL_DIR / "model_meta.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r") as f:
                        existing = json.load(f)
                    for key in ("accuracy_last_100", "win_rate_last_100", "predictions_tracked"):
                        if key in existing:
                            meta[key] = existing[key]
                except Exception:
                    pass
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            logger.info("Models saved to %s", MODEL_DIR)
        except Exception as e:
            logger.error("Failed to save models: %s", e)

    async def train(self, pool):
        """Full train on 7-day sliding window of trade outcomes."""
        try:
            from catboost import CatBoostClassifier
            from lightgbm import LGBMClassifier
            from xgboost import XGBClassifier
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
                feature_row = [features.get(col, 0) for col in FEATURE_COLUMNS]
                features_list.append(feature_row)
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
            logger.info("CatBoost trained successfully")
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
            logger.info("LightGBM trained successfully")
        except Exception as e:
            logger.error("LightGBM training failed: %s", e)
            return

        # XGBoost — shallower depth for inductive bias diversity
        try:
            neg_count = len(y) - y.sum()
            pos_count = y.sum()
            scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1.0

            self.xgb_model = XGBClassifier(
                n_estimators=500,
                max_depth=4,
                learning_rate=0.05,
                scale_pos_weight=scale_pos_weight,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                eval_metric="logloss",
                verbosity=0,
            )
            self.xgb_model.fit(X, y)
            logger.info("XGBoost trained successfully")
        except Exception as e:
            logger.error("XGBoost training failed: %s", e)
            return

        self.is_trained = True
        self.sample_count = len(X)
        self.last_train_time = time.time()
        self.last_update_time = time.time()
        self.trades_since_last_update = 0
        self.total_trades_trained = len(X)

        # FLAML auto-tuning when enough samples (4th ensemble member)
        if len(X) >= MIN_SAMPLES_PRODUCTION:
            logger.info("Running FLAML auto-tuning (60s budget, %d samples)...", len(X))
            try:
                from flaml import AutoML
                automl = AutoML()
                automl.fit(
                    X_train=X,
                    y_train=y,
                    task="classification",
                    metric="roc_auc",
                    time_budget=60,
                    estimator_list=["lgbm", "catboost", "xgboost"],
                    log_file_name=str(MODEL_DIR / "flaml_log.json"),
                    seed=42,
                    verbose=0,
                )
                best_estimator = automl.best_estimator
                best_config = automl.best_config
                logger.info(
                    "FLAML best estimator: %s | AUC: %.4f | config: %s",
                    best_estimator,
                    1.0 - automl.best_loss,
                    json.dumps(best_config, default=str)[:200],
                )
                self.flaml_model = automl.model.estimator
                self.best_flaml_config = best_config
                with open(MODEL_DIR / "flaml_model.pkl", "wb") as f:
                    pickle.dump(self.flaml_model, f)
            except ImportError:
                logger.info("FLAML not installed — skipping auto-tuning")
            except Exception as e:
                logger.warning("FLAML tuning failed: %s — using default configs", e)

        # SHAP feature importance (runs after full retrain only)
        try:
            import shap
            explainer = shap.TreeExplainer(self.lgbm_model)
            shap_values = explainer.shap_values(X)
            # For binary classification, shap_values[1] is positive class
            if isinstance(shap_values, list):
                shap_importance = shap_values[1]
            else:
                shap_importance = shap_values
            mean_abs_shap = np.abs(shap_importance).mean(axis=0)
            feature_importance = dict(zip(FEATURE_COLUMNS, mean_abs_shap.tolist()))
            feature_importance = dict(
                sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
            )
            self._feature_importance = feature_importance
            logger.info("SHAP top 5 features: %s", list(feature_importance.keys())[:5])
        except ImportError:
            logger.info("SHAP not installed — skipping feature importance")
            self._feature_importance = {}
        except Exception as e:
            logger.warning("SHAP computation failed: %s", e)
            self._feature_importance = {}

        self._save_models()
        ensemble_size = 3 + (1 if self.flaml_model else 0)
        logger.info("Training complete — %d-model ensemble ready", ensemble_size)

    def _incremental_update(self, X_new: pd.DataFrame, y_new: np.ndarray):
        """Append new boosting rounds to existing models without full retraining.
        Faster adaptation to recent market changes."""
        try:
            from catboost import CatBoostClassifier, Pool as CatPool
            import lightgbm as lgb
            from xgboost import XGBClassifier

            # CatBoost incremental — append 50 new trees
            cb_new = CatBoostClassifier(
                iterations=50,
                depth=6,
                learning_rate=0.05,
                auto_class_weights="Balanced",
                verbose=0,
                random_seed=42,
            )
            cb_new.fit(X_new, y_new, init_model=self.catboost_model)
            self.catboost_model = cb_new

            # LightGBM incremental — append 50 new trees via Booster
            new_data = lgb.Dataset(X_new, label=y_new)
            booster = self.lgbm_model.booster_
            self.lgbm_model._Booster = lgb.train(
                self.lgbm_model.get_params(),
                new_data,
                num_boost_round=50,
                init_model=booster,
            )

            # XGBoost incremental — append 50 new trees
            neg_count = len(y_new) - y_new.sum()
            pos_count = y_new.sum()
            spw = neg_count / pos_count if pos_count > 0 else 1.0
            xgb_new = XGBClassifier(
                n_estimators=50,
                max_depth=4,
                learning_rate=0.05,
                scale_pos_weight=spw,
                verbosity=0,
            )
            xgb_new.fit(X_new, y_new, xgb_model=self.xgb_model.get_booster())
            self.xgb_model = xgb_new

            self.trades_since_last_update = 0
            self.last_update_time = time.time()
            logger.info("Incremental update complete — appended 50 trees on %d samples", len(X_new))
            self._save_models()
        except Exception as e:
            logger.error("Incremental update failed: %s — will wait for full retrain", e)

    def predict(self, features: dict) -> tuple[float, bool]:
        """
        Predict probability of profitable trade (0-100 score).
        Returns (score, is_trained).
        When untrained, uses basic heuristics to generate meaningful scores
        so paper trading can collect data for the first real training run.
        """
        if not self.is_trained:
            return self._heuristic_score(features), False

        try:
            row = [features.get(col, 0) for col in FEATURE_COLUMNS]
            X = pd.DataFrame([row], columns=FEATURE_COLUMNS)

            probas = []
            for m in (self.catboost_model, self.lgbm_model, self.xgb_model):
                if m is not None:
                    probas.append(m.predict_proba(X)[0][1])

            # Add FLAML as 4th ensemble member if available
            if self.flaml_model is not None:
                try:
                    probas.append(self.flaml_model.predict_proba(X)[0][1])
                except Exception:
                    pass

            if not probas:
                return 50.0, False

            ensemble_proba = sum(probas) / len(probas)
            return round(ensemble_proba * 100, 1), True
        except Exception as e:
            logger.error("Prediction error: %s", e)
            return 50.0, False

    def _heuristic_score(self, features: dict) -> float:
        """Basic scoring heuristics for cold-start before ML model trains."""
        score = 55.0  # Base: slightly optimistic to generate data

        # Strong positive signals
        bsr = features.get("buy_sell_ratio_5min", 1.0)
        if bsr > 2.0:
            score += 10.0
        elif bsr > 1.5:
            score += 5.0
        elif bsr < 0.8:
            score -= 10.0

        # Liquidity health
        liq = features.get("liquidity_sol", 0)
        if liq > 20:
            score += 5.0
        elif liq < 3:
            score -= 15.0

        # Red flags — hard reject
        if features.get("bundle_detected", 0):
            return 10.0
        if features.get("fresh_wallet_ratio", 0) > 0.5:
            score -= 15.0
        if features.get("bot_transaction_ratio", 0) > 0.5:
            score -= 15.0

        # Creator history
        if features.get("creator_rug_count", 0) >= 3:
            return 10.0

        # Holder diversity
        top10 = features.get("top10_holder_pct", 0)
        if top10 > 50:
            score -= 10.0
        elif 0 < top10 < 25:
            score += 5.0

        return max(0.0, min(100.0, round(score, 1)))

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

            score, is_trained = model.predict(features)
            response = {
                "request_id": request_id,
                "ml_score": score,
                "model_trained": is_trained,
                "sample_count": model.sample_count,
            }
            await redis_conn.publish("ml:score_response", json.dumps(response))
        except Exception as e:
            logger.error("Scoring request error: %s", e)


def _build_features_from_rows(rows) -> tuple[pd.DataFrame, np.ndarray]:
    """Convert DB rows to X, y for training/incremental update."""
    features_list = []
    labels = []
    for row in rows:
        try:
            features = json.loads(row["features_json"])
            feature_row = [features.get(col, 0) for col in FEATURE_COLUMNS]
            features_list.append(feature_row)
            labels.append(1 if row["outcome"] == "profit" else 0)
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    if not features_list:
        return pd.DataFrame(columns=FEATURE_COLUMNS), np.array([])
    return pd.DataFrame(features_list, columns=FEATURE_COLUMNS), np.array(labels)


# --- Retrain loop ---
async def _retrain_loop(model: MLModel):
    """
    Two-tier retrain system:
    - Incremental update every 50 new labeled trades (append 50 trees)
    - Full retrain weekly (reset to fresh models on 7-day window)
    - Cold start: check every hour for enough samples (>= 50)
    """
    pool = await get_pool()
    while True:
        try:
            now = time.time()
            full_retrain_due = (now - model.last_train_time) >= RETRAIN_INTERVAL_SECONDS

            if not model.is_trained:
                # Cold start: check for enough samples
                seven_days_ago = datetime.now(timezone.utc).timestamp() - (7 * 86400)
                count = await pool.fetchval(
                    "SELECT COUNT(*) FROM trades WHERE created_at > $1 AND features_json IS NOT NULL AND outcome IS NOT NULL",
                    seven_days_ago,
                )
                if count >= MIN_SAMPLES_FIRST_TRAIN:
                    logger.info("Cold start: %d samples available (need %d) — training now", count, MIN_SAMPLES_FIRST_TRAIN)
                    await model.train(pool)
                else:
                    logger.info("Cold start: %d/%d samples — waiting for more paper trades", count, MIN_SAMPLES_FIRST_TRAIN)

            elif full_retrain_due:
                logger.info("Weekly full retrain triggered")
                await model.train(pool)

            elif model.is_trained:
                # Check for incremental update: new trades since last update
                try:
                    rows = await pool.fetch(
                        """SELECT features_json, outcome FROM trades
                           WHERE closed_at > $1 AND features_json IS NOT NULL AND outcome IS NOT NULL
                           ORDER BY closed_at DESC""",
                        model.last_update_time,
                    )
                except Exception as e:
                    logger.debug("Incremental check DB error: %s", e)
                    rows = []

                if len(rows) >= INCREMENTAL_UPDATE_INTERVAL:
                    logger.info("Incremental update triggered — %d new samples since last update", len(rows))
                    X_new, y_new = _build_features_from_rows(rows)
                    if len(X_new) >= 10:
                        # Run in executor to avoid blocking event loop
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, model._incremental_update, X_new, y_new)
                        model.total_trades_trained += len(X_new)
                        logger.info("Total trades trained: %d", model.total_trades_trained)

        except Exception as e:
            logger.error("Retrain loop error: %s", e)

        # Check every hour
        await asyncio.sleep(3600)


# --- Outcome listener for drift detection ---
async def _update_accuracy_tracking(ml_score: float, outcome: int, redis_conn: aioredis.Redis):
    """Track rolling accuracy of last 100 predictions."""
    entry = json.dumps({
        "score": ml_score,
        "outcome": outcome,
        "timestamp": time.time(),
    })
    await redis_conn.lpush("ml:prediction_history", entry)
    await redis_conn.ltrim("ml:prediction_history", 0, 99)

    # Recompute accuracy
    history_raw = await redis_conn.lrange("ml:prediction_history", 0, -1)
    history = [json.loads(h) for h in history_raw]

    if len(history) >= 10:
        correct = sum(
            1 for h in history
            if (h["score"] >= 65) == bool(h["outcome"])
        )
        accuracy = correct / len(history)

        taken = [h for h in history if h["score"] >= 65]
        win_rate = (
            sum(1 for h in taken if h["outcome"] == 1) / len(taken)
            if taken else 0
        )

        try:
            meta_path = MODEL_DIR / "model_meta.json"
            if meta_path.exists():
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                meta["accuracy_last_100"] = round(accuracy * 100, 1)
                meta["win_rate_last_100"] = round(win_rate * 100, 1)
                meta["predictions_tracked"] = len(history)
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)
        except Exception as e:
            logger.debug("Meta accuracy update failed: %s", e)


async def _outcome_listener(model: MLModel, redis_conn: aioredis.Redis | None):
    """Listen for trade outcomes: update drift detector + accuracy tracking."""
    if not redis_conn:
        return

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("trades:outcome")
    logger.info("Listening for trade outcomes on trades:outcome (drift + accuracy)")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            ml_score = float(data.get("ml_score", 50.0))
            outcome = 1 if data.get("outcome") == "profit" else 0

            # Update accuracy tracking
            await _update_accuracy_tracking(ml_score, outcome, redis_conn)

            # Update drift detector
            drift = model.drift_detector.update(ml_score, outcome)
            if drift:
                # Publish emergency retrain signal
                await redis_conn.publish("ml:emergency_retrain", json.dumps({
                    "reason": "ADWIN drift detected",
                    "drift_count": model.drift_detector.drift_count,
                    "timestamp": time.time(),
                }))
        except Exception as e:
            logger.error("Outcome listener error: %s", e)


# --- Emergency retrain listener ---
async def _emergency_retrain_listener(model: MLModel, redis_conn: aioredis.Redis | None):
    """Listen for emergency retrain signals (from ADWIN drift or manual trigger)."""
    if not redis_conn:
        return

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("ml:emergency_retrain")
    logger.info("Listening for emergency retrain signals")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            reason = data.get("reason", "unknown")
            logger.warning("Emergency retrain triggered: %s", reason)

            pool = await get_pool()
            await model.train(pool)
            logger.info("Emergency retrain complete")
        except Exception as e:
            logger.error("Emergency retrain error: %s", e)


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
        _outcome_listener(model, redis_conn),
        _emergency_retrain_listener(model, redis_conn),
    )


if __name__ == "__main__":
    asyncio.run(main())
