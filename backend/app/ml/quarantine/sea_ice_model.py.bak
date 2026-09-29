"""
POLAR-AI Sea Ice Forecasting Model
Random Forest baseline with feature engineering.
Architecture designed to be swapped with ConvLSTM for production use.
"""
import numpy as np
import math
from typing import Dict, List, Tuple, Optional


class SeaIceBaselineModel:
    """
    Persistence + physics-informed baseline for sea ice forecasting.
    Uses a simple but principled model when sklearn RF isn't trained.
    
    Approach:
    - Persistence (last known value) as baseline
    - Seasonal climatology correction
    - Spatial gradient smoothing
    """

    def predict(
        self,
        lat: float, lon: float,
        current_sic: float,
        horizon_hours: int,
        wind_speed: float = 8.0,
        temperature: float = -15.0,
        current_u: float = 0.2,
    ) -> Dict:
        """
        Predict sea ice concentration at a location for given horizon.
        
        Returns dict with:
        - predicted_concentration: float [0,1]
        - uncertainty: float
        - confidence: float
        """
        import math
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        doy = now.timetuple().tm_yday

        # Seasonal component
        horizon_days = horizon_hours / 24.0
        future_doy = (doy + horizon_days) % 365
        seasonal_now = 0.5 + 0.5 * math.cos(2 * math.pi * (doy - 210) / 365)
        seasonal_future = 0.5 + 0.5 * math.cos(2 * math.pi * (future_doy - 210) / 365)
        seasonal_delta = seasonal_future - seasonal_now

        # Temperature effect: warmer → less ice
        temp_effect = -0.005 * max(0, temperature + 2)

        # Wind effect: strong winds can compact or disperse ice
        wind_effect = -0.002 * max(0, wind_speed - 8)

        # Ocean current effect: strong currents advect ice
        current_effect = -0.01 * current_u

        lat_factor = float(np.clip((abs(lat) - 55) / 25, 0, 1))

        # Prediction
        delta = (
            lat_factor * seasonal_delta * 0.3 +
            temp_effect * (horizon_days / 7) +
            wind_effect * (horizon_days / 7) +
            current_effect * (horizon_days / 7)
        )

        predicted = float(np.clip(current_sic + delta, 0, 1))

        # Uncertainty grows with horizon
        uncertainty = 0.03 + (horizon_hours / 168.0) * 0.12

        # Confidence decreases with horizon
        confidence = max(0.4, 1.0 - (horizon_hours / 168.0) * 0.55)

        return {
            "predicted_concentration": round(predicted, 4),
            "uncertainty": round(uncertainty, 4),
            "confidence": round(confidence, 4),
            "model": "physics_baseline_v1",
        }


class RandomForestSeaIceModel:
    """
    Random Forest sea ice forecasting model.
    Trained on tabular features extracted from gridded data.
    
    Features:
    - lat_factor, seasonal, lon_factor
    - sic_t (current), sic_t1 (yesterday), sic_t2, sic_t7
    - wind_speed, wind_dir, temperature
    - current_u, current_v, sst
    
    Targets: sic at +24h, +48h, +72h
    """

    def __init__(self, model_path: str = None):
        self.model_24h = None
        self.model_48h = None
        self.model_72h = None
        self.is_trained = False
        self.baseline = SeaIceBaselineModel()

        if model_path:
            self._load(model_path)

    def _load(self, model_path: str):
        try:
            import joblib
            self.model_24h = joblib.load(f"{model_path}/rf_24h.pkl")
            self.model_48h = joblib.load(f"{model_path}/rf_48h.pkl")
            self.model_72h = joblib.load(f"{model_path}/rf_72h.pkl")
            self.is_trained = True
        except Exception as e:
            print(f"  ⚠️  Could not load RF model: {e}. Using physics baseline.")

    def _make_features(self, lat, lon, sic_t, sic_t1, sic_t2, sic_t7,
                       wind_speed, wind_dir, temp, current_u, current_v, sst):
        """Build feature vector for a single prediction."""
        from datetime import datetime, timezone
        import math
        doy = datetime.now(timezone.utc).timetuple().tm_yday
        lat_factor = float(np.clip((abs(lat) - 55) / 25, 0, 1))
        seasonal = 0.5 + 0.5 * math.cos(2 * math.pi * (doy - 210) / 365)
        lon_cos = math.cos(math.radians(lon))
        lon_sin = math.sin(math.radians(lon))
        wind_u = wind_speed * math.cos(math.radians(wind_dir))
        wind_v = wind_speed * math.sin(math.radians(wind_dir))

        return [
            lat_factor, seasonal, lon_cos, lon_sin,
            sic_t, sic_t1, sic_t2, sic_t7,
            wind_u, wind_v, temp,
            current_u, current_v, sst,
            sic_t - sic_t1,  # 1-day trend
            sic_t - sic_t7,  # 7-day trend
        ]

    def predict(self, lat, lon, horizon_hours, **features):
        """Predict SIC for given location and horizon."""
        if not self.is_trained:
            return self.baseline.predict(
                lat, lon,
                features.get("sic_t", 0.5),
                horizon_hours,
                features.get("wind_speed", 8),
                features.get("temp", -15),
                features.get("current_u", 0.2),
            )

        feat = self._make_features(
            lat, lon,
            features.get("sic_t", 0.5),
            features.get("sic_t1", 0.5),
            features.get("sic_t2", 0.5),
            features.get("sic_t7", 0.5),
            features.get("wind_speed", 8),
            features.get("wind_dir", 270),
            features.get("temp", -15),
            features.get("current_u", 0.2),
            features.get("current_v", 0.0),
            features.get("sst", 2.0),
        )

        feat_arr = np.array([feat])
        if horizon_hours <= 24 and self.model_24h:
            pred = float(self.model_24h.predict(feat_arr)[0])
        elif horizon_hours <= 48 and self.model_48h:
            pred = float(self.model_48h.predict(feat_arr)[0])
        else:
            pred = float(self.model_72h.predict(feat_arr)[0]) if self.model_72h else 0.5

        pred = float(np.clip(pred, 0, 1))
        uncertainty = 0.03 + (horizon_hours / 168.0) * 0.12
        confidence = max(0.4, 1.0 - (horizon_hours / 168.0) * 0.55)

        return {
            "predicted_concentration": round(pred, 4),
            "uncertainty": round(uncertainty, 4),
            "confidence": round(confidence, 4),
            "model": "random_forest_v1",
        }


# Singleton model instance
_model = None


def get_model(model_dir: str = None) -> RandomForestSeaIceModel:
    """Get or create model instance."""
    global _model
    if _model is None:
        if model_dir:
            _model = RandomForestSeaIceModel(model_dir)
        else:
            _model = RandomForestSeaIceModel()
    return _model
