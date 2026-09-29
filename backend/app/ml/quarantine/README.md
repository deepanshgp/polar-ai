# Quarantined legacy ML files

These files were moved here during Phase 5 migration:

| File | Original location | Reason quarantined |
|------|-------------------|--------------------|
| `sea_ice_model.py.bak` | `app/ml/sea_ice_model.py` | Replaced by `seaice_pixel.py` and `seaice_unet.py`. `SeaIceBaselineModel` and `RandomForestSeaIceModel` are superseded. `get_model()` singleton was never called by any service. |
| `train_sea_ice.py.bak` | `app/ml/train_sea_ice.py` | Used `sklearn.model_selection.train_test_split(random_state=42)` — a random split on synthetic data with spatiotemporal leakage. Replaced by `scripts/train_sea_ice.py` which uses `make_time_split` + `assert_no_leakage`. |

**What was preserved from the old files:**
- Feature engineering ideas (lat_factor, seasonal cosine, wind decomposition) informed the `seaice_pixel.py` feature set.
- The `_make_features` pattern carried forward (now in `_build_features_single`).
- The `joblib.dump` serialisation pattern is retained in `seaice_pixel.py`.

**What was NOT preserved:**
- The random split (`train_test_split(random_state=42)`) — leaky, replaced.
- The hardcoded uncertainty formula (`0.03 + horizon/168 * 0.12`) — replaced by held-out evaluation.
- `SeaIceBaselineModel` — now handled by `app/evaluation/seaice_baselines.py`.

See `docs/DECISIONS.md §Phase 5` for the full decision record.
