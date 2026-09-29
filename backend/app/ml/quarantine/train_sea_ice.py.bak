"""
POLAR-AI Sea Ice Model Training Script

Trains Random Forest models for 24h, 48h, 72h SIC forecasting.
Uses features from data_pipeline/create_demo_data.py output.

Usage:
  python -m app.ml.train_sea_ice
  python -m app.ml.train_sea_ice --features data/demo/ml_features.csv
"""
import argparse
import os
import json
import numpy as np
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
MODELS_DIR = BASE_DIR / "models"
DEMO_FEATURES = BASE_DIR / "data" / "demo" / "ml_features.csv"


def train_model(features_path: str = None, models_dir: str = None):
    """
    Train Random Forest sea ice models.
    
    Args:
        features_path: Path to ML features CSV
        models_dir: Directory to save trained models
    """
    if features_path is None:
        features_path = str(DEMO_FEATURES)
    if models_dir is None:
        models_dir = str(MODELS_DIR)

    os.makedirs(models_dir, exist_ok=True)

    print(f"\n🤖 Training Sea Ice Forecasting Models")
    print(f"   Features: {features_path}")
    print(f"   Models dir: {models_dir}")

    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        from sklearn.model_selection import train_test_split
        import joblib
    except ImportError as e:
        print(f"  ✗ sklearn not available: {e}")
        return

    # Load features
    if not os.path.exists(features_path):
        print(f"  ✗ Features file not found: {features_path}")
        print("    Run: python -m data_pipeline.run_pipeline --demo-only")
        return

    df = pd.read_csv(features_path)
    print(f"  Loaded {len(df)} samples")

    feature_cols = [
        "lat_factor", "seasonal", "sic_t", "sic_t1", "sic_t2", "sic_t7",
        "wind_speed", "wind_dir", "temp", "current_u", "current_v", "sst",
    ]

    # Derived features
    df["sic_1d_trend"] = df["sic_t"] - df["sic_t1"]
    df["sic_7d_trend"] = df["sic_t"] - df["sic_t7"]
    df["lon_cos"] = np.cos(np.radians(df["lon"]))
    df["lon_sin"] = np.sin(np.radians(df["lon"]))
    feature_cols += ["sic_1d_trend", "sic_7d_trend", "lon_cos", "lon_sin"]

    X = df[feature_cols].values
    metrics = {}

    for horizon, target_col in [("24h", "target_24h"), ("48h", "target_48h"), ("72h", "target_72h")]:
        y = df[target_col].values

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Train RF (lightweight settings for fast training)
        rf = RandomForestRegressor(
            n_estimators=50,
            max_depth=8,
            min_samples_leaf=5,
            n_jobs=-1,
            random_state=42,
        )
        rf.fit(X_train, y_train)

        y_pred = rf.predict(X_test)
        y_pred = np.clip(y_pred, 0, 1)

        mae = float(mean_absolute_error(y_test, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))

        # Persistence baseline (predict same as current)
        y_persistence = X_test[:, feature_cols.index("sic_t")]
        persistence_mae = float(mean_absolute_error(y_test, y_persistence))
        skill_score = 1 - mae / persistence_mae if persistence_mae > 0 else 0

        metrics[horizon] = {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "persistence_mae": round(persistence_mae, 4),
            "skill_score": round(skill_score, 4),
            "n_train": len(X_train),
            "n_test": len(X_test),
        }

        # Save model
        model_path = os.path.join(models_dir, f"rf_{horizon}.pkl")
        joblib.dump(rf, model_path)
        print(f"  ✓ {horizon}: MAE={mae:.4f}, RMSE={rmse:.4f}, Skill={skill_score:.3f} → {model_path}")

    # Save metrics
    metrics_path = os.path.join(models_dir, "sea_ice_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  ✓ Metrics saved: {metrics_path}")
    print(f"\n✅ Sea ice model training complete!")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=str, default=None)
    parser.add_argument("--models-dir", type=str, default=None)
    args = parser.parse_args()
    train_model(args.features, args.models_dir)
