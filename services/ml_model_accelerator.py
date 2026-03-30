"""
ZMN Bot — Accelerated ML Engine (TabPFN + CatBoost + LightGBM)
================================================================
3-phase model that scales with data volume:
  Phase 1 (n < 250):  TabPFN only — optimal for small data, zero tuning
  Phase 2 (250-999):  TabPFN + regularized CatBoost ensemble
  Phase 3 (n >= 1000): Full TabPFN + CatBoost + LightGBM ensemble

Hard-reject rules override ML for known rug vectors.
Drop-in replacement for existing ml_engine.py scoring via Redis pub/sub.
"""

import asyncio
import json
import logging
import os
import pickle
import time
from pathlib import Path

import aiohttp
import numpy as np
import pandas as pd
import redis.asyncio as aioredis
from dotenv import load_dotenv
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder

from services.db import get_pool

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("zmn_ml_accelerator")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

MODEL_DIR = Path("data/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# --- Feature schema (25 core features used by accelerated engine) ---
# Must match what signal_aggregator sends in features dict.
# Superset features from ml_engine.py's 44-column FEATURE_COLUMNS are
# handled gracefully: extras are ignored, missing default to -1.
FEATURE_SCHEMA = [
    "liquidity_sol",
    "buy_sell_ratio_5min",
    "bonding_curve_progress",
    "holder_count",
    "top10_holder_pct",
    "dev_wallet_hold_pct",
    "bundle_detected",
    "fresh_wallet_ratio",
    "creator_prev_launches",
    "creator_rug_rate",
    "mint_authority_revoked",
    "token_age_seconds",
    "market_cap_usd",
    "cfgi_score",
    "sol_price_usd",
    "nansen_sm_count",
    # Additional features from existing ml_engine.py that improve accuracy
    "liquidity_velocity",
    "unique_buyers_30min",
    "volume_acceleration_15min",
    "dev_sold_pct",
    "bot_transaction_ratio",
    "bundled_supply_pct",
    "creator_rug_count",
    "nansen_sm_inflow_ratio",
    "nansen_concentration_risk",
]

# Existing ml_engine.py thresholds — kept compatible
ML_THRESHOLDS = {
    "speed_demon": 65,
    "analyst": 70,
    "whale_tracker": 70,
}
ML_THRESHOLD_ADJUSTMENTS = {
    "FRENZY": -5,
    "DEFENSIVE": 10,
}

# Minimum samples before upgrading from heuristic to trained model
MIN_SAMPLES_FIRST_TRAIN = 15
MIN_SAMPLES_PRODUCTION = 200
RETRAIN_INTERVAL_SECONDS = 7 * 24 * 3600


# --- Hard rules that override ML (domain knowledge filter) ---
def apply_hard_rules(features: dict) -> tuple[bool, str]:
    """Returns (should_reject, reason). Hard rules override ML."""
    if not features.get("mint_authority_revoked", True):
        return True, "mint_authority_not_revoked"
    if features.get("dev_wallet_hold_pct", 0) > 15.0:
        return True, "dev_wallet_hold_pct_too_high"
    if features.get("creator_rug_rate", 0) > 0.5:
        return True, "creator_rug_rate_too_high"
    if features.get("bundle_detected", False) and features.get("fresh_wallet_ratio", 0) > 0.7:
        return True, "bundle_with_fresh_wallets"
    return False, ""


class AcceleratedMLEngine:
    """
    3-phase ML engine:
    Phase 1 (n < 250): TabPFN only (sweet spot for small data)
    Phase 2 (250 <= n < 1000): TabPFN + regularized CatBoost ensemble
    Phase 3 (n >= 1000): Full TabPFN + CatBoost + LightGBM ensemble
    """

    def __init__(self, model_dir=None, use_binary=True):
        self.model_dir = Path(model_dir) if model_dir else MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.use_binary = use_binary  # True = win/not-win; False = win/loss/breakeven
        self.le = LabelEncoder()
        self.models: dict = {}
        self.phase = 0
        self.n_samples = 0
        self.is_trained = False
        self.sample_count = 0
        self.last_train_time = 0.0
        self.cv_auc_mean = 0.0
        self.cv_auc_std = 0.0
        self._load()

    def _get_phase(self, n_samples):
        if n_samples < 250:
            return 1
        elif n_samples < 1000:
            return 2
        else:
            return 3

    def _make_tabpfn(self):
        from tabpfn import TabPFNClassifier  # noqa: may not be installed
        return TabPFNClassifier()

    def _make_catboost(self, n_samples):
        from catboost import CatBoostClassifier
        depth = 2 if n_samples < 500 else (3 if n_samples < 1000 else 4)
        iters = 50 if n_samples < 500 else (100 if n_samples < 1000 else 300)
        return CatBoostClassifier(
            iterations=iters,
            depth=depth,
            learning_rate=0.03,
            l2_leaf_reg=5.0,
            boosting_type="Ordered",
            auto_class_weights="Balanced",
            verbose=0,
            random_seed=42,
        )

    def _make_lgbm(self):
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.03,
            num_leaves=8,
            min_child_samples=10,
            reg_alpha=1.0,
            reg_lambda=5.0,
            class_weight="balanced",
            verbose=-1,
            random_state=42,
        )

    def train_from_dataframe(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Train the appropriate model(s) based on sample count."""
        self.n_samples = len(X)
        self.phase = self._get_phase(self.n_samples)

        if self.use_binary:
            y = y.map(lambda v: 1 if v == "win" or v == "profit" or v == 1 else 0)

        y_encoded = self.le.fit_transform(y)

        # Build feature matrix from schema — missing features default to -1
        X_clean = pd.DataFrame()
        for col in FEATURE_SCHEMA:
            X_clean[col] = X[col] if col in X.columns else -1
        X_clean = X_clean.fillna(-1)

        logger.info("Training Phase %d with %d samples (%.1f%% positive)",
                     self.phase, self.n_samples, y_encoded.mean() * 100)

        if self.phase >= 1:
            try:
                tabpfn = self._make_tabpfn()
                tabpfn.fit(X_clean.values, y_encoded)
                self.models["tabpfn"] = tabpfn
                logger.info("TabPFN fitted successfully on %d samples", len(X_clean))
            except ImportError:
                logger.warning(
                    "TabPFN not installed — running without it. "
                    "Install with: pip install tabpfn"
                )
            except Exception as e:
                logger.warning("TabPFN training failed: %s", e)

        if self.phase >= 2:
            try:
                cb = self._make_catboost(self.n_samples)
                cb.fit(X_clean.values, y_encoded)
                self.models["catboost"] = cb
                logger.info("CatBoost (regularized) trained successfully")
            except Exception as e:
                logger.error("CatBoost training failed: %s", e)

        if self.phase >= 3:
            try:
                lgbm = self._make_lgbm()
                lgbm.fit(X_clean.values, y_encoded)
                self.models["lightgbm"] = lgbm
                logger.info("LightGBM trained successfully")
            except Exception as e:
                logger.error("LightGBM training failed: %s", e)

        if not self.models:
            logger.error("No models trained successfully")
            return {"phase": self.phase, "n_samples": self.n_samples, "cv_auc_mean": 0.0, "cv_auc_std": 0.0}

        # Cross-validation score
        n_folds = min(5, max(2, self.n_samples // 30))
        cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
        primary_name = "tabpfn" if self.phase == 1 else "catboost"
        primary = self.models.get(primary_name, list(self.models.values())[0])
        try:
            scores = cross_val_score(primary, X_clean.values, y_encoded, cv=cv, scoring="roc_auc")
            self.cv_auc_mean = float(scores.mean())
            self.cv_auc_std = float(scores.std())
            logger.info("CV AUC: %.4f +/- %.4f (%d-fold)", self.cv_auc_mean, self.cv_auc_std, n_folds)
        except Exception as e:
            logger.warning("Cross-validation failed: %s", e)
            self.cv_auc_mean = 0.0
            self.cv_auc_std = 0.0

        self.is_trained = True
        self.sample_count = self.n_samples
        self.last_train_time = time.time()
        self.save()

        return {
            "phase": self.phase,
            "n_samples": self.n_samples,
            "cv_auc_mean": self.cv_auc_mean,
            "cv_auc_std": self.cv_auc_std,
        }

    async def train(self, pool):
        """Train from PostgreSQL trades table — compatible with existing ml_engine.py."""
        from datetime import datetime, timezone
        seven_days_ago = datetime.now(timezone.utc).timestamp() - (7 * 86400)

        try:
            rows = await pool.fetch(
                """SELECT features_json, outcome FROM trades
                   WHERE created_at > $1 AND features_json IS NOT NULL AND outcome IS NOT NULL""",
                seven_days_ago,
            )
        except Exception:
            rows = []

        # Also try paper_trades
        try:
            paper_rows = await pool.fetch(
                """SELECT features_json, outcome FROM paper_trades
                   WHERE created_at > $1 AND features_json IS NOT NULL AND outcome IS NOT NULL""",
                seven_days_ago,
            )
            rows = list(rows) + list(paper_rows)
        except Exception:
            pass

        if len(rows) < MIN_SAMPLES_FIRST_TRAIN:
            logger.info("Only %d samples (need %d) — skipping training", len(rows), MIN_SAMPLES_FIRST_TRAIN)
            return

        features_list = []
        labels = []
        for row in rows:
            try:
                features = json.loads(row["features_json"])
                features_list.append(features)
                labels.append("win" if row["outcome"] == "profit" else "loss")
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        if len(features_list) < MIN_SAMPLES_FIRST_TRAIN:
            return

        X = pd.DataFrame(features_list)
        y = pd.Series(labels)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.train_from_dataframe, X, y)
        logger.info("Training result: %s", result)

    def predict(self, features: dict) -> tuple[float, bool]:
        """
        Score a single token. Returns (score 0-100, is_trained).
        Compatible with existing ml_engine.py predict() interface.
        """
        if not self.is_trained or not self.models:
            return self._heuristic_score(features), False

        # Hard rules first
        reject, reason = apply_hard_rules(features)
        if reject:
            logger.debug("Hard rule reject: %s", reason)
            return 8.0, True  # Low score = definite skip

        X = pd.DataFrame([{col: features.get(col, -1) for col in FEATURE_SCHEMA}])
        X = X.fillna(-1)

        # Log feature coverage for diagnosis (every 50th call to avoid spam)
        if not hasattr(self, '_predict_count'):
            self._predict_count = 0
        self._predict_count += 1
        if self._predict_count % 50 == 1:
            populated = sum(1 for col in FEATURE_SCHEMA if features.get(col, -1) not in (-1, 0, 0.0))
            logger.info("ML feature coverage: %d/%d populated (%.0f%%), liq=%.1f bc=%.2f age=%ds",
                        populated, len(FEATURE_SCHEMA),
                        populated / len(FEATURE_SCHEMA) * 100,
                        features.get("liquidity_sol", 0),
                        features.get("bonding_curve_progress", 0),
                        int(features.get("token_age_seconds", 0)))

        try:
            if self.phase == 1 and "tabpfn" in self.models:
                proba = self.models["tabpfn"].predict_proba(X.values)[0]
                method = "tabpfn"
            elif self.phase == 2:
                if "tabpfn" in self.models and "catboost" in self.models:
                    p_tabpfn = self.models["tabpfn"].predict_proba(X.values)[0]
                    p_cb = self.models["catboost"].predict_proba(X.values)[0]
                    proba = 0.60 * p_tabpfn + 0.40 * p_cb
                    method = "tabpfn+catboost"
                elif "catboost" in self.models:
                    proba = self.models["catboost"].predict_proba(X.values)[0]
                    method = "catboost"
                    logger.debug("Phase 2 scoring without TabPFN")
                elif "tabpfn" in self.models:
                    proba = self.models["tabpfn"].predict_proba(X.values)[0]
                    method = "tabpfn"
                else:
                    return 50.0, False
            else:
                if "tabpfn" in self.models:
                    p_tabpfn = self.models["tabpfn"].predict_proba(X.values)[0]
                    p_cb = self.models["catboost"].predict_proba(X.values)[0]
                    p_lgbm = self.models["lightgbm"].predict_proba(X.values)[0]
                    proba = (0.35 * p_tabpfn +
                             0.35 * p_cb +
                             0.30 * p_lgbm)
                    method = "tabpfn+catboost+lightgbm"
                else:
                    # TabPFN unavailable — equal weight remaining models
                    p_cb = self.models["catboost"].predict_proba(X.values)[0]
                    p_lgbm = self.models["lightgbm"].predict_proba(X.values)[0]
                    proba = 0.50 * p_cb + 0.50 * p_lgbm
                    method = "catboost+lightgbm"
                    logger.debug("Phase 3 scoring without TabPFN")

            # For binary classification: proba[1] is P(win)
            if len(proba) == 2:
                score = float(proba[1]) * 100.0
            else:
                score = float(np.max(proba)) * 100.0

            return round(max(5.0, min(95.0, score)), 1), True

        except Exception as e:
            logger.error("Prediction error (%s): %s", method if "method" in dir() else "unknown", e)
            return 50.0, False

    def predict_detailed(self, features: dict) -> dict:
        """Extended prediction with method info. Used by training scripts."""
        reject, reason = apply_hard_rules(features)
        if reject:
            return {
                "prediction": "loss",
                "confidence": 0.95,
                "method": f"hard_rule:{reason}",
                "phase": self.phase,
                "score": 8.0,
            }

        score, is_trained = self.predict(features)
        return {
            "prediction": "win" if score >= 65 else "loss",
            "confidence": score / 100.0,
            "method": f"phase{self.phase}",
            "phase": self.phase,
            "score": score,
            "is_trained": is_trained,
        }

    def _heuristic_score(self, features: dict) -> float:
        """Bootstrap scoring — identical to existing ml_engine.py heuristic."""
        import random as _r
        score = 50.0

        if features.get("bundle_detected", 0):
            return _r.uniform(5.0, 15.0)
        if features.get("creator_rug_count", 0) >= 3:
            return _r.uniform(5.0, 15.0)
        if features.get("fresh_wallet_ratio", 0) > 0.6:
            return _r.uniform(10.0, 20.0)
        if features.get("dev_sold_pct", 0) > 20:
            return _r.uniform(10.0, 20.0)

        bsr = features.get("buy_sell_ratio_5min", 1.0)
        liq = features.get("liquidity_sol", 0)
        top10 = features.get("top10_holder_pct", 50)
        nansen_flow = features.get("nansen_sm_inflow_ratio", 1.0)
        strong = sum([bsr > 2.5, liq > 15, top10 < 20, nansen_flow > 1.5])
        if strong >= 3:
            return _r.uniform(72.0, 88.0)

        if bsr < 0.9:       score -= 15.0
        elif bsr > 1.8:     score += 12.0
        elif bsr > 1.3:     score += 6.0

        if liq < 3:         score -= 20.0
        elif liq < 7:       score -= 8.0
        elif liq > 20:      score += 8.0

        if top10 > 60:      score -= 15.0
        elif top10 > 40:    score -= 7.0
        elif top10 < 20:    score += 10.0

        if features.get("bot_transaction_ratio", 0) > 0.4: score -= 12.0
        if features.get("mint_authority_revoked", 0) == 0:  score -= 8.0
        if nansen_flow > 1.3:  score += 10.0
        elif nansen_flow < 0.7: score -= 8.0

        score += _r.uniform(-3.0, 3.0)
        return max(5.0, min(95.0, round(score, 1)))

    def passes_threshold(self, score: float, personality: str, market_mode: str = "NORMAL") -> bool:
        """Check if ML score passes the threshold for a personality."""
        base = ML_THRESHOLDS.get(personality, 70)
        adjustment = ML_THRESHOLD_ADJUSTMENTS.get(market_mode, 0)
        threshold = base + adjustment
        return score >= threshold

    def save(self):
        path = self.model_dir / "accelerated_model.pkl"
        try:
            with open(path, "wb") as f:
                pickle.dump({
                    "models": self.models,
                    "le": self.le,
                    "phase": self.phase,
                    "n_samples": self.n_samples,
                    "cv_auc_mean": self.cv_auc_mean,
                    "cv_auc_std": self.cv_auc_std,
                    "last_train_time": self.last_train_time,
                }, f)
            # Also save meta JSON for dashboard compatibility
            meta = {
                "engine": "accelerated",
                "phase": self.phase,
                "sample_count": self.n_samples,
                "cv_auc_mean": self.cv_auc_mean,
                "cv_auc_std": self.cv_auc_std,
                "last_train_time": self.last_train_time,
                "models_active": list(self.models.keys()),
                "features": FEATURE_SCHEMA,
                "feature_count": len(FEATURE_SCHEMA),
            }
            with open(self.model_dir / "model_meta.json", "w") as f:
                json.dump(meta, f, indent=2)
            logger.info("Accelerated model saved (phase=%d, n=%d)", self.phase, self.n_samples)
        except Exception as e:
            logger.error("Failed to save accelerated model: %s", e)

    def _load(self):
        path = self.model_dir / "accelerated_model.pkl"
        if not path.exists():
            return
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            self.models = data["models"]
            self.le = data["le"]
            self.phase = data["phase"]
            self.n_samples = data["n_samples"]
            self.sample_count = self.n_samples
            self.cv_auc_mean = data.get("cv_auc_mean", 0.0)
            self.cv_auc_std = data.get("cv_auc_std", 0.0)
            self.last_train_time = data.get("last_train_time", 0.0)
            self.is_trained = bool(self.models)
            logger.info("Loaded accelerated model: phase=%d, n=%d, AUC=%.4f",
                        self.phase, self.n_samples, self.cv_auc_mean)
        except Exception as e:
            logger.warning("Failed to load accelerated model: %s", e)


# --- RugCheck API enrichment (optional, adds 2 features) ---
async def enrich_rugcheck(mint_address: str, session: "aiohttp.ClientSession") -> dict:
    """Fetch RugCheck score for a token. Returns dict with 2 extra features."""
    try:
        async with session.get(
            f"https://api.rugcheck.xyz/tokens/{mint_address}/report",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {
                    "rugcheck_score": data.get("score", -1),
                    "rugcheck_risk_count": len(data.get("risks", [])),
                }
    except Exception:
        pass
    return {"rugcheck_score": -1, "rugcheck_risk_count": -1}


# --- Scoring listener (drop-in replacement for ml_engine._scoring_listener) ---
async def _scoring_listener(engine: AcceleratedMLEngine, redis_conn: aioredis.Redis | None):
    """Listen for scoring requests on Redis and respond with ML scores."""
    if not redis_conn:
        logger.info("No Redis — scoring listener disabled")
        return

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("ml:score_request")
    logger.info("Accelerated ML listening for score requests on ml:score_request")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                request_id = data.get("request_id", "unknown")
                features = data.get("features", {})

                score, is_trained = engine.predict(features)
                response = {
                    "request_id": request_id,
                    "ml_score": score,
                    "model_trained": is_trained,
                    "sample_count": engine.sample_count,
                    "phase": engine.phase,
                }
                await redis_conn.publish("ml:score_response", json.dumps(response))
            except Exception as e:
                logger.error("Scoring request error: %s", e)
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


# --- Retrain loop ---
async def _retrain_loop(engine: AcceleratedMLEngine):
    """Retrain periodically from DB."""
    pool = await get_pool()
    while True:
        check_interval = 3600
        try:
            now = time.time()
            full_retrain_due = (now - engine.last_train_time) >= RETRAIN_INTERVAL_SECONDS

            if not engine.is_trained:
                await engine.train(pool)
                check_interval = 300  # 5 min during cold start
            elif full_retrain_due:
                logger.info("Weekly full retrain triggered")
                await engine.train(pool)
        except Exception as e:
            logger.error("Retrain loop error: %s", e)
            check_interval = 300

        await asyncio.sleep(check_interval)


# --- Outcome listener (drift detection) ---
async def _outcome_listener(engine: AcceleratedMLEngine, redis_conn: aioredis.Redis | None):
    """Listen for trade outcomes — update accuracy tracking."""
    if not redis_conn:
        return

    pubsub = redis_conn.pubsub()
    await pubsub.subscribe("trades:outcome")
    logger.info("Listening for trade outcomes on trades:outcome")

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                ml_score = float(data.get("ml_score", 50.0))
                outcome = 1 if data.get("outcome") == "profit" else 0

                entry = json.dumps({
                    "score": ml_score,
                    "outcome": outcome,
                    "timestamp": time.time(),
                })
                await redis_conn.lpush("ml:prediction_history", entry)
                await redis_conn.ltrim("ml:prediction_history", 0, 99)
            except Exception as e:
                logger.error("Outcome listener error: %s", e)
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


# --- Main entry point ---
async def main():
    logger.info("Accelerated ML Engine starting (TEST_MODE=%s)", TEST_MODE)

    engine = AcceleratedMLEngine()

    # Attempt initial training if not yet trained
    pool = await get_pool()
    if not engine.is_trained:
        await engine.train(pool)

    # Connect Redis
    redis_conn = None
    try:
        redis_conn = aioredis.from_url(REDIS_URL, decode_responses=True, max_connections=5)
        await redis_conn.ping()
        await redis_conn.set("ml:engine:mode", "accelerated")
        logger.info("Redis connected, ml:engine:mode=accelerated")
    except Exception as e:
        logger.warning("Redis connection failed: %s — scoring disabled", e)

    await asyncio.gather(
        _scoring_listener(engine, redis_conn),
        _retrain_loop(engine),
        _outcome_listener(engine, redis_conn),
    )


if __name__ == "__main__":
    asyncio.run(main())
