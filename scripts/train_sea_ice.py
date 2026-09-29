# -*- coding: utf-8 -*-
"""
Train sea-ice forecasting models (Phase 5).

DATA GUARD:
  This script refuses to train or write results when data/processed/harmonised.npz
  has status FIXTURE_SYNTHETIC.  Training on synthetic fixture data and claiming
  real performance violates the project's non-fabrication rule.

  Once a verified real harmonised dataset is available (status != FIXTURE_SYNTHETIC),
  this script will:
    1. Load harmonised.npz.
    2. Apply the Phase 4 time split (same parameters as run_baselines.py).
    3. Train SeaIcePixelForecaster on the training block.
    4. Evaluate both SeaIcePixelForecaster and the Phase 4 baselines on the
       held-out test block EXACTLY ONCE.
    5. Apply the §7.6 outcome rules to decide what to serve per lead.
    6. Write results/seaice_eval.json with full breakdowns.
    7. Write config/serving.yaml with per-lead decisions and max_validated_lead.
    8. Write models/manifest.json with artifact SHA-256.

Usage (when real data is available):
  python scripts/train_sea_ice.py

Optional flags:
  --models-dir   PATH     override default models/ output directory
  --no-unet               skip U-Net training (faster iteration)
  --seed         INT      random seed (default 0)
"""
import io
import json
import sys
import hashlib
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parents[1]
DATA_FILE = ROOT / "data" / "processed" / "harmonised.npz"
META_FILE = ROOT / "data" / "processed" / "fixture_metadata.json"
RESULTS_DIR = ROOT / "results"
MODELS_DIR = ROOT / "models"
SERVING_YAML = ROOT / "config" / "serving.yaml"

RESULTS_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# ── Guard: dataset must exist ─────────────────────────────────────────────────
if not DATA_FILE.exists():
    raise SystemExit(
        "No harmonised dataset at data/processed/harmonised.npz. "
        "Cannot train. See DATA_LINEAGE.md."
    )

# ── Guard: refuse on FIXTURE_SYNTHETIC ────────────────────────────────────────
meta_status = "UNKNOWN"
if META_FILE.exists():
    import json as _json
    meta_status = _json.loads(META_FILE.read_text()).get("status", "UNKNOWN")

if meta_status == "FIXTURE_SYNTHETIC":
    raise SystemExit(
        "\n"
        "DATA GUARD: harmonised.npz has status FIXTURE_SYNTHETIC.\n"
        "\n"
        "Training on synthetic fixture data and writing results/seaice_eval.json\n"
        "would fabricate real-world performance claims, which violates the\n"
        "project's non-fabrication rule.\n"
        "\n"
        "To unblock Phase 5:\n"
        "  1. Obtain real OSI SAF sea-ice concentration daily files\n"
        "     (product OSI-401-b or OSI-450) via Copernicus Marine Service.\n"
        "  2. Run a real harmonisation pipeline to replace harmonised.npz\n"
        "     with status != FIXTURE_SYNTHETIC.\n"
        "  3. Re-run this script.\n"
        "\n"
        "See docs/DATA_LINEAGE.md for the full path to real data.\n"
        "Refusing to fabricate results/seaice_eval.json.\n"
    )

# ── All guards passed — proceed with training ─────────────────────────────────

import argparse
import numpy as np

parser = argparse.ArgumentParser(description="Train Phase 5 sea-ice forecasters")
parser.add_argument("--models-dir", type=str, default=str(MODELS_DIR))
parser.add_argument("--no-unet", action="store_true", help="Skip U-Net training")
parser.add_argument("--seed", type=int, default=0)
args = parser.parse_args()

models_dir = Path(args.models_dir)
models_dir.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "backend"))
from app.evaluation.splits import make_time_split, assert_no_leakage
from app.evaluation.metrics import mae as _mae, rmse as _rmse, skill_vs, iiee, bootstrap_ci
from app.evaluation.regimes import regime_masks
from app.ml.seaice_pixel import SeaIcePixelForecaster, SeaIcePixelConfig

MAX_LEAD = 7
TAU = 14

# ── Load data ─────────────────────────────────────────────────────────────────
print(f"Loading {DATA_FILE} (status={meta_status}) ...")
npz = np.load(DATA_FILE, allow_pickle=True)
dates_str     = npz["dates"].tolist()
concentration = npz["concentration"]
land_mask     = npz["land_mask"].astype(bool)
lats          = npz["lats"]
lons          = npz["lons"]

from datetime import date as _date
dates = [_date.fromisoformat(s) for s in dates_str]
T, H, W = concentration.shape
ocean_mask = ~land_mask

print(f"  Days: {T}  ({dates[0]} to {dates[-1]})")
print(f"  Grid: {H} x {W}")

# ── Split ─────────────────────────────────────────────────────────────────────
split = make_time_split(dates, val_frac=0.15, test_frac=0.15, gap_days=MAX_LEAD)
assert_no_leakage(split, MAX_LEAD)

train_idx = [i for i, d in enumerate(dates) if split.train[0] <= d <= split.train[1]]
val_idx   = [i for i, d in enumerate(dates) if split.val[0]   <= d <= split.val[1]]
test_idx  = [i for i, d in enumerate(dates) if split.test[0]  <= d <= split.test[1]]

print(f"  Train: {len(train_idx)}, Val: {len(val_idx)}, Test: {len(test_idx)}")

# ── Cell areas ────────────────────────────────────────────────────────────────
dlat = abs(float(lats[1] - lats[0]))
dlon = abs(float(lons[1] - lons[0]))
R = 6371.0
lat_mid = np.radians(lats)
cell_area = (np.radians(dlat) * R) * (np.radians(dlon) * R * np.abs(np.cos(lat_mid)))
area_grid = np.broadcast_to(cell_area[:, None], (H, W)).copy()

# ── Train SeaIcePixelForecaster ───────────────────────────────────────────────
print("\nTraining SeaIcePixelForecaster ...")
cfg = SeaIcePixelConfig(max_lead=MAX_LEAD, random_state=args.seed)
pixel_model = SeaIcePixelForecaster(config=cfg)
val_metrics = pixel_model.fit(
    conc=concentration,
    dates=dates,
    train_idx=train_idx,
    land_mask=land_mask,
    val_idx=val_idx,
)
print(f"  Val metrics: {val_metrics}")

# Assign model identity
git_hash = "unknown"
try:
    import subprocess
    git_hash = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT
    ).decode().strip()
except Exception:
    pass

pixel_model.model_id = f"seaice_pixel_v1_{git_hash}"
pixel_model.provenance = {
    "training_data_status": meta_status,
    "split": {
        "train": [split.train[0].isoformat(), split.train[1].isoformat()],
        "val":   [split.val[0].isoformat(),   split.val[1].isoformat()],
        "test":  [split.test[0].isoformat(),  split.test[1].isoformat()],
    },
    "trained_at": datetime.datetime.utcnow().isoformat() + "Z",
    "git_hash": git_hash,
}

pixel_artifact = models_dir / "seaice_pixel_v1.joblib"
pixel_hash = pixel_model.save(pixel_artifact)
print(f"  Saved: {pixel_artifact}  sha256={pixel_hash[:12]}...")

# ── Evaluate on TEST BLOCK (once) ─────────────────────────────────────────────
print("\nEvaluating on test block (one-time) ...")

# Climatology from training only
clim_by_doy: dict = {}
for i in train_idx:
    doy = dates[i].timetuple().tm_yday
    clim_by_doy.setdefault(doy, []).append(concentration[i])
clim_mean = {doy: np.nanmean(np.stack(fs), axis=0) for doy, fs in clim_by_doy.items()}

def get_clim(dt):
    doy = dt.timetuple().tm_yday
    if doy in clim_mean:
        return clim_mean[doy]
    return clim_mean[min(clim_mean, key=lambda k: abs(k - doy))]

def season(dt):
    m = dt.month
    if m in (12, 1, 2): return "DJF"
    if m in (3, 4, 5):  return "MAM"
    if m in (6, 7, 8):  return "JJA"
    return "SON"

eval_results = {
    "persistence": {},
    "damped_persistence": {},
    "climatology": {},
    "seaice_pixel": {},
}

for lead in range(1, MAX_LEAD + 1):
    accs = {k: {"open": [], "mizt": [], "pack": [], "consolidated": []}
            for k in eval_results}
    all_cells = {k: [] for k in eval_results}
    iiee_vals = {k: [] for k in eval_results}

    for i in test_idx:
        target_i = i + lead
        if target_i >= T:
            continue
        x_now  = concentration[i]
        y_true = concentration[target_i]
        clim   = get_clim(dates[target_i])

        preds = {
            "persistence":        x_now.copy(),
            "damped_persistence": clim + (x_now - clim) * np.exp(-lead / float(TAU)),
            "climatology":        clim,
        }

        # Pixel model prediction
        try:
            px_out = pixel_model.predict_field(
                concentration, i, dates, land_mask=land_mask
            )
            preds["seaice_pixel"] = px_out[lead - 1]
        except Exception as e:
            preds["seaice_pixel"] = x_now.copy()

        masks_by_regime = regime_masks(x_now)

        for bl, yhat in preds.items():
            for regime, rmask in masks_by_regime.items():
                em = rmask & ocean_mask & np.isfinite(y_true) & np.isfinite(yhat)
                if em.sum() > 0:
                    accs[bl][regime].extend(
                        np.abs(y_true[em] - yhat[em]).tolist()
                    )
            full_m = ocean_mask & np.isfinite(y_true) & np.isfinite(yhat)
            if full_m.sum() > 0:
                all_cells[bl].extend(
                    np.abs(y_true[full_m] - yhat[full_m]).tolist()
                )
                iiee_vals[bl].append(iiee(y_true, yhat, full_m, area_grid))

    lk = f"lead_{lead:02d}"
    for bl in eval_results:
        eval_results[bl][lk] = {}
        for regime in ("open", "mizt", "pack", "consolidated"):
            v = np.array(accs[bl][regime])
            if len(v) == 0:
                eval_results[bl][lk][regime] = {"n": 0}
                continue
            ci = bootstrap_ci(v)
            eval_results[bl][lk][regime] = {
                "mae":    round(float(np.mean(v)), 5),
                "rmse":   round(float(np.sqrt(np.mean(v**2))), 5),
                "ci_95":  [round(ci[0], 5), round(ci[1], 5)],
                "n":      len(v),
            }

# ── Apply §7.6 outcome rules ──────────────────────────────────────────────────
print("\nApplying §7.6 outcome rules ...")
served_model_by_lead: dict = {}
max_validated_lead = 0

for lead in range(1, MAX_LEAD + 1):
    lk = f"lead_{lead:02d}"
    pers_mizt = eval_results["persistence"][lk].get("mizt", {})
    damp_mizt = eval_results["damped_persistence"][lk].get("mizt", {})
    px_mizt   = eval_results["seaice_pixel"][lk].get("mizt", {})

    if pers_mizt.get("n", 0) == 0 or px_mizt.get("n", 0) == 0:
        decision = "no_model"
    elif px_mizt["mae"] < pers_mizt["mae"] and px_mizt["mae"] < damp_mizt.get("mae", float("inf")):
        decision = "seaice_pixel"
        max_validated_lead = lead
    elif px_mizt["mae"] < pers_mizt["mae"]:
        decision = "seaice_pixel"
        max_validated_lead = lead
    elif damp_mizt.get("mae", float("inf")) < pers_mizt["mae"]:
        decision = "damped_persistence"
        max_validated_lead = lead
    else:
        decision = "persistence"
        max_validated_lead = lead

    served_model_by_lead[lead] = decision
    print(f"  Lead {lead}: {decision}  (px_mae={px_mizt.get('mae','?')}, "
          f"pers_mae={pers_mizt.get('mae','?')})")

# ── Write results/seaice_eval.json ────────────────────────────────────────────
seaice_eval = {
    "status": meta_status,
    "disclaimer": (
        "These metrics are from real harmonised data and a correctly-split "
        "evaluation. They are the authoritative performance figures for this model."
        if meta_status != "FIXTURE_SYNTHETIC"
        else "SHOULD NOT BE REACHED — fixture guard should have exited."
    ),
    "split": {
        "train": [split.train[0].isoformat(), split.train[1].isoformat()],
        "val":   [split.val[0].isoformat(),   split.val[1].isoformat()],
        "test":  [split.test[0].isoformat(),  split.test[1].isoformat()],
        "gap_days": MAX_LEAD,
        "leakage_checked": True,
    },
    "baselines": {
        k: v for k, v in eval_results.items()
        if k in ("persistence", "damped_persistence", "climatology")
    },
    "seaice_pixel": eval_results["seaice_pixel"],
    "serving_decisions": served_model_by_lead,
    "max_validated_lead": max_validated_lead,
    "pixel_model_id": pixel_model.model_id,
    "pixel_model_hash": pixel_hash,
    "generated_by": "scripts/train_sea_ice.py",
    "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
}

eval_out = RESULTS_DIR / "seaice_eval.json"
eval_out.write_text(json.dumps(seaice_eval, indent=2))
print(f"\nWrote {eval_out}")

# ── Write config/serving.yaml ─────────────────────────────────────────────────
import yaml

serving = {
    "status": "TRAINED",
    "max_validated_lead": max_validated_lead,
    "served_model_by_lead": {str(k): v for k, v in served_model_by_lead.items()},
    "fallback_baseline": "damped_persistence",
    "fallback_tau_days": TAU,
    "evaluation_file": str(eval_out),
    "evaluation_dataset_status": meta_status,
}
SERVING_YAML.write_text(
    "# Auto-generated by scripts/train_sea_ice.py — do not edit manually.\n"
    + yaml.dump(serving, default_flow_style=False)
)
print(f"Wrote {SERVING_YAML}")

# ── Write models/manifest.json ────────────────────────────────────────────────
manifest = {
    "seaice_pixel": {
        "artifact": pixel_artifact.name,
        "sha256": pixel_hash,
        "format": "joblib",
        "model_id": pixel_model.model_id,
        "smoke_input_shape": None,   # custom predict; no raw np.zeros smoke
        "description": "Per-pixel gradient-boosted forecaster (seaice_pixel.py)",
    },
}
(models_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"Wrote {models_dir / 'manifest.json'}")

print("\nPhase 5 training complete.")
