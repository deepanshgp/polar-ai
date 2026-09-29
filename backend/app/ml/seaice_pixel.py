"""
Per-pixel gradient-boosted sea-ice forecaster (§7.2).

Predicts the *change from persistence* per lead, per pixel, using lagged local
features.  This is the cheap, strong baseline before the U-Net.

DATA GUARD:
  Training requires data/processed/harmonised.npz with status != FIXTURE_SYNTHETIC.
  The class itself can be instantiated at any time; the guard is in
  scripts/train_sea_ice.py, not here.

Architecture:
  - Features per pixel per sample:
    * sic at t, t-1, t-2, t-3, t-6 (5 lags)
    * 3x3 neighbourhood mean at t (spatial context)
    * wind_u, wind_v, temp2m at t (forcing; NaN-safe, filled with 0)
    * sin(2pi*doy/365), cos(2pi*doy/365) (seasonality)
  - Target: sic[t+lead] - sic[t]  (delta from persistence)
  - One independent estimator per lead (1..7).
  - Model: HistGradientBoostingRegressor (handles NaN natively).
  - Prediction: persistence[t] + clamp(delta_pred, -1, 1), then clamp to [0,1].
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

MAX_LEAD = 7
N_LAGS = 5
LAG_STEPS = [1, 2, 3, 4, 7]    # in days
NEIGH_RADIUS = 1                # 3x3 neighbourhood


@dataclass
class SeaIcePixelConfig:
    max_lead: int = MAX_LEAD
    learning_rate: float = 0.05
    max_iter: int = 300
    max_depth: int = 6
    min_samples_leaf: int = 20
    l2_regularization: float = 1.0
    random_state: int = 0


def _neighbourhood_mean(field: np.ndarray, r: int = 1) -> np.ndarray:
    """Compute (H, W) neighbourhood mean ignoring NaN."""
    from scipy.ndimage import uniform_filter
    filled = np.where(np.isnan(field), 0.0, field)
    count  = np.where(np.isnan(field), 0.0, 1.0)
    s_fld  = uniform_filter(filled, size=2*r+1, mode="nearest")
    s_cnt  = uniform_filter(count,  size=2*r+1, mode="nearest")
    with np.errstate(invalid="ignore"):
        return np.where(s_cnt > 0, s_fld / s_cnt, np.nan)


def _build_features_single(
    conc: np.ndarray,   # (T, H, W) — concentration cube
    t: int,             # issue-time index
    doy: int,
    wind_u: Optional[np.ndarray] = None,    # (H, W) at t
    wind_v: Optional[np.ndarray] = None,
    temp2m: Optional[np.ndarray] = None,
    land_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Build feature matrix (N_ocean_pixels, n_features) for one issue time."""
    H, W = conc.shape[1], conc.shape[2]

    # Lagged concentrations — fill lags that fall before t=0 with t=0
    lags = []
    for lag in LAG_STEPS:
        idx = max(0, t - lag)
        lags.append(conc[idx])     # (H, W)

    neigh = _neighbourhood_mean(conc[t])  # (H, W)

    # Seasonal encoding
    sin_doy = np.full((H, W), np.sin(2 * np.pi * doy / 365.25))
    cos_doy = np.full((H, W), np.cos(2 * np.pi * doy / 365.25))

    # Forcing (NaN-safe)
    wu = wind_u if wind_u is not None else np.zeros((H, W))
    wv = wind_v if wind_v is not None else np.zeros((H, W))
    tp = temp2m if temp2m is not None else np.zeros((H, W))
    wu = np.nan_to_num(wu, nan=0.0)
    wv = np.nan_to_num(wv, nan=0.0)
    tp = np.nan_to_num(tp, nan=0.0)

    # Stack into (n_features, H, W) then reshape to (H*W, n_features)
    layers = [conc[t]] + lags + [neigh, wu, wv, tp, sin_doy, cos_doy]
    cube   = np.stack(layers, axis=0)          # (n_feat, H, W)
    flat   = cube.reshape(len(layers), -1).T   # (H*W, n_feat)

    # Mask land
    if land_mask is not None:
        ocean = ~land_mask.ravel()
        flat = flat[ocean]

    return flat.astype(np.float32)


class SeaIcePixelForecaster:
    """
    Per-pixel gradient-boosted sea-ice forecaster.

    Attributes:
        max_lead  (int)   — maximum lead day (read by the serving stack).
        model_id  (str)   — filled after training.
        model_hash(str)   — SHA-256 of the serialised artifact.
    """

    max_lead = MAX_LEAD

    def __init__(self, config: Optional[SeaIcePixelConfig] = None):
        self.config = config or SeaIcePixelConfig()
        self._estimators: Dict[int, Any] = {}   # lead -> fitted estimator
        self.model_id: str = ""
        self.model_hash: str = ""
        self.provenance: dict = {}

    # ── Training ──────────────────────────────────────────────────────────────

    def fit(
        self,
        conc: np.ndarray,         # (T, H, W)
        dates,                    # list[date], length T
        train_idx: List[int],
        land_mask: Optional[np.ndarray] = None,
        wind_u: Optional[np.ndarray] = None,  # (T, H, W)
        wind_v: Optional[np.ndarray] = None,
        temp2m: Optional[np.ndarray] = None,
        val_idx: Optional[List[int]] = None,
    ) -> Dict[str, float]:
        """
        Fit one estimator per lead on the training block.

        Returns {f"lead_{l}_val_mae": float} for monitoring.
        """
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
        except ImportError as exc:
            raise ImportError(
                "scikit-learn required for SeaIcePixelForecaster.fit()"
            ) from exc

        T, H, W = conc.shape
        cfg = self.config
        val_metrics: Dict[str, float] = {}

        for lead in range(1, cfg.max_lead + 1):
            X_list, y_list = [], []
            for i in train_idx:
                target_i = i + lead
                if target_i >= T:
                    continue
                doy = dates[i].timetuple().tm_yday
                wu = wind_u[i] if wind_u is not None else None
                wv = wind_v[i] if wind_v is not None else None
                tp = temp2m[i] if temp2m is not None else None
                X_i = _build_features_single(conc, i, doy, wu, wv, tp, land_mask)
                # Target: delta from persistence
                delta = conc[target_i] - conc[i]
                if land_mask is not None:
                    y_i = delta[~land_mask].ravel()
                else:
                    y_i = delta.ravel()
                X_list.append(X_i)
                y_list.append(y_i.astype(np.float32))

            if not X_list:
                logger.warning("Lead %d: no training samples, skipping", lead)
                continue

            X = np.concatenate(X_list, axis=0)
            y = np.concatenate(y_list, axis=0)
            valid = np.isfinite(y)
            X, y = X[valid], y[valid]
            logger.info("Lead %d: fitting on %d pixels", lead, len(y))

            est = HistGradientBoostingRegressor(
                learning_rate=cfg.learning_rate,
                max_iter=cfg.max_iter,
                max_depth=cfg.max_depth,
                min_samples_leaf=cfg.min_samples_leaf,
                l2_regularization=cfg.l2_regularization,
                random_state=cfg.random_state,
            )
            est.fit(X, y)
            self._estimators[lead] = est

            # Val MAE
            if val_idx:
                errs = []
                for i in val_idx:
                    target_i = i + lead
                    if target_i >= T:
                        continue
                    doy = dates[i].timetuple().tm_yday
                    wu = wind_u[i] if wind_u is not None else None
                    wv = wind_v[i] if wind_v is not None else None
                    tp = temp2m[i] if temp2m is not None else None
                    X_i = _build_features_single(conc, i, doy, wu, wv, tp, land_mask)
                    delta_hat = est.predict(X_i)
                    if land_mask is not None:
                        sic_now = conc[i][~land_mask].ravel()
                        sic_true = conc[target_i][~land_mask].ravel()
                    else:
                        sic_now = conc[i].ravel()
                        sic_true = conc[target_i].ravel()
                    sic_pred = np.clip(sic_now + delta_hat, 0.0, 1.0)
                    err = np.abs(sic_true - sic_pred)
                    errs.extend(err[np.isfinite(err)].tolist())
                if errs:
                    val_metrics[f"lead_{lead:02d}_val_mae"] = float(np.mean(errs))

        return val_metrics

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict_field(
        self,
        conc: np.ndarray,        # (T, H, W) — history available at issue time
        issue_idx: int,
        dates,
        land_mask: Optional[np.ndarray] = None,
        wind_u: Optional[np.ndarray] = None,
        wind_v: Optional[np.ndarray] = None,
        temp2m: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Predict SIC for all leads, returning (L, H, W).
        Land cells are NaN.  Output is clamped to [0, 1].
        """
        H, W = conc.shape[1], conc.shape[2]
        doy = dates[issue_idx].timetuple().tm_yday
        wu = wind_u[issue_idx] if wind_u is not None else None
        wv = wind_v[issue_idx] if wind_v is not None else None
        tp = temp2m[issue_idx] if temp2m is not None else None

        X = _build_features_single(conc, issue_idx, doy, wu, wv, tp, land_mask)
        sic_now = conc[issue_idx].copy()

        out = np.full((self.config.max_lead, H, W), np.nan)
        if land_mask is not None:
            ocean_flat = ~land_mask.ravel()
            sic_now_flat = sic_now[~land_mask].ravel()
        else:
            ocean_flat = np.ones(H * W, bool)
            sic_now_flat = sic_now.ravel()

        for lead in range(1, self.config.max_lead + 1):
            if lead not in self._estimators:
                # Fall back to persistence
                field = sic_now.copy()
                if land_mask is not None:
                    field[land_mask] = np.nan
                out[lead - 1] = field
                continue

            delta = self._estimators[lead].predict(X)
            pred_flat = np.clip(sic_now_flat + delta, 0.0, 1.0)

            full = np.full(H * W, np.nan)
            full[ocean_flat] = pred_flat
            out[lead - 1] = full.reshape(H, W)

        return out

    # ── Serialisation ─────────────────────────────────────────────────────────

    def save(self, path: Path) -> str:
        """Save artifact, return SHA-256."""
        import joblib
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.model_hash = digest
        return digest

    @classmethod
    def load(cls, path: Path) -> "SeaIcePixelForecaster":
        import joblib
        return joblib.load(path)

    def __repr__(self):
        leads = sorted(self._estimators)
        return (
            f"SeaIcePixelForecaster(trained_leads={leads}, "
            f"model_id={self.model_id!r})"
        )
