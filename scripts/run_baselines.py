# -*- coding: utf-8 -*-
"""
Run all Phase 4 baselines and write results/baselines.json.

DATA PROVENANCE:
  Reads data/processed/harmonised.npz, which must have been produced by
  scripts/build_fixture_dataset.py or an equivalent Phase-3 pipeline.
  The fixture_metadata.json in the same directory is loaded and embedded
  in the results so the provenance is always co-located with the metrics.

SPLITS:
  Time-based (70 / 15 / 15) with a 7-day gap (= max lead) so no target
  value in the validation block was visible at any training time step.
  assert_no_leakage() is called and will raise if the invariant is broken.

SEA-ICE BASELINES (per §6.2):
  - persistence         : last observed field, unchanged for all leads
  - climatology         : training-set day-of-year mean
  - damped_persistence  : exponential decay toward climatology (τ = 14 d)

ICEBERG BASELINES (per §6.3):
  - stationary          : predict p0 for every lead
  - constant_velocity   : extrapolate last observed velocity

METRICS (per §6.4):
  - MAE, RMSE in SIC units [0, 1]
  - IIEE in km² (using flat-Earth cell areas from the latitude grid)
  - Skill vs persistence for the other two baselines
  - Bootstrap 95% CI (n=1000, seed=0)

REGIMES (per §6.5):
  open [0, 0.15), mizt [0.15, 0.50), pack [0.50, 0.85),
  consolidated [0.85, 1.0)   — defined from the input field (no leakage).

SEASONS:
  DJF (Dec-Jan-Feb), MAM, JJA, SON — derived from test-block dates.

OUTPUT:
  results/baselines.json  — all metrics, sample counts, provenance.
"""

import io
import json
import sys
import numpy as np
from datetime import date, timedelta
from pathlib import Path

# Ensure Unicode output works on Windows cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parents[1]
DATA_FILE = ROOT / "data" / "processed" / "harmonised.npz"
META_FILE = ROOT / "data" / "processed" / "fixture_metadata.json"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)
OUT_FILE = RESULTS_DIR / "baselines.json"

# ── Guard ─────────────────────────────────────────────────────────────────────
if not DATA_FILE.exists():
    raise SystemExit(
        "No verified harmonised dataset at data/processed/harmonised.npz; "
        "refusing to fabricate results/baselines.json. "
        "Run scripts/build_fixture_dataset.py first."
    )

# ── Load evaluation modules ────────────────────────────────────────────────────
sys.path.insert(0, str(ROOT / "backend"))
from app.evaluation.splits import make_time_split, assert_no_leakage, make_berg_split
from app.evaluation.seaice_baselines import persistence, climatology, damped_persistence
from app.evaluation.iceberg_baselines import stationary, constant_velocity
from app.evaluation.metrics import mae, rmse, skill_vs, iiee, bootstrap_ci
from app.evaluation.regimes import regime_masks

MAX_LEAD = 7
TAU = 14          # damped-persistence decay constant [days]

# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading harmonised dataset …")
npz = np.load(DATA_FILE, allow_pickle=True)
dates_str = npz["dates"].tolist()
concentration = npz["concentration"]    # (T, H, W) float32
land_mask = npz["land_mask"].astype(bool)  # (H, W)
lats = npz["lats"]                      # (H,)
lons = npz["lons"]                      # (W,)
berg_records = json.loads(str(npz["berg_records"]))

metadata_status = "UNKNOWN"
if META_FILE.exists():
    meta = json.loads(META_FILE.read_text())
    metadata_status = meta.get("status", "UNKNOWN")

print(f"  Status  : {metadata_status}")
print(f"  Days    : {len(dates_str)}  ({dates_str[0]} to {dates_str[-1]})")
print(f"  Grid    : {concentration.shape[1]} x {concentration.shape[2]}")
print(f"  Bergs   : {len(set(r['berg_id'] for r in berg_records))}")

dates = [date.fromisoformat(s) for s in dates_str]
T, H, W = concentration.shape
ocean_mask = ~land_mask                 # True = valid ocean cell

# ── Cell areas (flat-Earth approx using mid-latitude) ─────────────────────────
dlat = abs(float(lats[1] - lats[0]))   # degrees
dlon = abs(float(lons[1] - lons[0]))
R = 6371.0                              # km
lat_mid = np.radians(lats)
cell_area = (np.radians(dlat) * R) * (np.radians(dlon) * R * np.abs(np.cos(lat_mid)))
area_grid = np.broadcast_to(cell_area[:, None], (H, W)).copy()  # (H, W), km²

# ── Time split ─────────────────────────────────────────────────────────────────
print("Building time split …")
split = make_time_split(dates, val_frac=0.15, test_frac=0.15, gap_days=MAX_LEAD)
assert_no_leakage(split, MAX_LEAD)
print(f"  Train: {split.train[0]} → {split.train[1]}")
print(f"  Val:   {split.val[0]}   → {split.val[1]}")
print(f"  Test:  {split.test[0]} → {split.test[1]}")

train_idx = [i for i, d in enumerate(dates) if split.train[0] <= d <= split.train[1]]
val_idx   = [i for i, d in enumerate(dates) if split.val[0]   <= d <= split.val[1]]
test_idx  = [i for i, d in enumerate(dates) if split.test[0]  <= d <= split.test[1]]

print(f"  n_train={len(train_idx)}, n_val={len(val_idx)}, n_test={len(test_idx)}")

train_dates = [dates[i] for i in train_idx]
train_conc  = concentration[train_idx]
test_conc   = concentration[test_idx]
test_dates  = [dates[i] for i in test_idx]

# ── Climatology (training block only) ─────────────────────────────────────────
print("Computing climatology …")
clim_by_doy = {}
for d, f in zip(train_dates, train_conc):
    doy = d.timetuple().tm_yday
    clim_by_doy.setdefault(doy, []).append(f)
clim_mean = {doy: np.nanmean(np.stack(fs, axis=0), axis=0) for doy, fs in clim_by_doy.items()}

def get_clim(dt: date) -> np.ndarray:
    doy = dt.timetuple().tm_yday
    if doy in clim_mean:
        return clim_mean[doy]
    # fallback: nearest doy
    nearest = min(clim_mean, key=lambda k: abs(k - doy))
    return clim_mean[nearest]

# ── Season helper ──────────────────────────────────────────────────────────────
def season(dt: date) -> str:
    m = dt.month
    if m in (12, 1, 2):  return "DJF"
    if m in (3, 4, 5):   return "MAM"
    if m in (6, 7, 8):   return "JJA"
    return "SON"

# ── Sea-ice evaluation ─────────────────────────────────────────────────────────
print("Evaluating sea-ice baselines …")

# We need test samples where the "input" (issue time) is in the test block and
# the target is issue+lead days later.  We index by issue date in test_idx.
# If issue+lead goes beyond the array, skip.

def run_seaice_eval():
    results = {
        "persistence": {},
        "damped_persistence": {},
        "climatology": {},
    }

    for lead in range(1, MAX_LEAD + 1):
        # Collect per-sample residuals per regime per season
        acc = {bl: {r: {s: [] for s in ("DJF","MAM","JJA","SON")}
                    for r in ("open","mizt","pack","consolidated")}
               for bl in results}
        all_cells = {bl: {s: [] for s in ("DJF","MAM","JJA","SON")} for bl in results}
        iiee_acc  = {bl: {s: [] for s in ("DJF","MAM","JJA","SON")} for bl in results}

        for i in test_idx:
            target_i = i + lead
            if target_i >= T:
                continue
            issue_date  = dates[i]
            target_date = dates[target_i]
            x_now   = concentration[i]          # (H,W) — input (issue time)
            y_true  = concentration[target_i]   # (H,W) — target
            clim    = get_clim(target_date)     # (H,W)

            preds = {
                "persistence":        persistence(x_now, lead),
                "damped_persistence": damped_persistence(x_now, clim, lead, TAU),
                "climatology":        clim,
            }

            masks_by_regime = regime_masks(x_now)   # from issue-time field (no leakage)
            s = season(issue_date)

            for bl, yhat in preds.items():
                for regime, rmask in masks_by_regime.items():
                    eval_mask = rmask & ocean_mask
                    if eval_mask.sum() == 0:
                        continue
                    err = np.abs(y_true[eval_mask] - yhat[eval_mask])
                    acc[bl][regime][s].extend(err.tolist())

                # full-domain (ocean only)
                full_mask = ocean_mask & np.isfinite(y_true) & np.isfinite(yhat)
                if full_mask.sum() > 0:
                    all_cells[bl][s].extend(
                        np.abs(y_true[full_mask] - yhat[full_mask]).tolist()
                    )
                    iiee_val = iiee(y_true, yhat, full_mask, area_grid)
                    iiee_acc[bl][s].append(iiee_val)

        # Summarise
        for bl in results:
            lead_key = f"lead_{lead:02d}"
            results[bl][lead_key] = {}

            # Per-regime MAE + bootstrapped CI
            for regime in ("open", "mizt", "pack", "consolidated"):
                vals = []
                for s in ("DJF","MAM","JJA","SON"):
                    vals.extend(acc[bl][regime][s])
                n = len(vals)
                if n == 0:
                    results[bl][lead_key][regime] = {"n": 0}
                    continue
                v = np.array(vals)
                ci = bootstrap_ci(v)
                results[bl][lead_key][regime] = {
                    "mae": round(float(np.mean(v)), 5),
                    "rmse": round(float(np.sqrt(np.mean(v**2))), 5),
                    "ci_95": [round(ci[0],5), round(ci[1],5)],
                    "n": n,
                }

            # Seasonal full-domain
            seasonal = {}
            for s in ("DJF","MAM","JJA","SON"):
                all_v = np.array(all_cells[bl][s])
                iiee_v = np.array(iiee_acc[bl][s])
                if len(all_v) == 0:
                    seasonal[s] = {"n": 0}
                    continue
                ci = bootstrap_ci(all_v)
                seasonal[s] = {
                    "mae": round(float(np.mean(all_v)), 5),
                    "rmse": round(float(np.sqrt(np.mean(all_v**2))), 5),
                    "ci_95": [round(ci[0],5), round(ci[1],5)],
                    "iiee_km2_mean": round(float(np.mean(iiee_v)), 1) if len(iiee_v) else None,
                    "n_samples": len(iiee_v),
                    "n_cells": int(len(all_v)),
                }
            results[bl][lead_key]["seasonal"] = seasonal

    # Cross-baseline skill scores
    print("  Computing skill scores vs persistence …")
    skill_results = {}
    for lead in range(1, MAX_LEAD + 1):
        lead_key = f"lead_{lead:02d}"
        skill_results[lead_key] = {}
        per_mae = {bl: {} for bl in ("damped_persistence","climatology")}
        for bl in ("damped_persistence","climatology"):
            for regime in ("open","mizt","pack","consolidated"):
                bl_data = results[bl][lead_key][regime]
                p_data  = results["persistence"][lead_key][regime]
                if bl_data.get("n",0) == 0 or p_data.get("n",0) == 0:
                    continue
                sk = skill_vs(p_data["mae"], bl_data["mae"])
                per_mae[bl][regime] = round(sk, 5)
        skill_results[lead_key] = per_mae

    return results, skill_results

seaice_results, skill_results = run_seaice_eval()

# ── Iceberg evaluation ─────────────────────────────────────────────────────────
print("Evaluating iceberg baselines …")

berg_split = make_berg_split(berg_records, val_frac=0.15, test_frac=0.15)
test_bergs = set(berg_split["test"])

# Group records by berg_id
by_berg = {}
for r in berg_records:
    by_berg.setdefault(r["berg_id"], []).append(r)
for bid in by_berg:
    by_berg[bid].sort(key=lambda r: r["date"])

def run_berg_eval():
    results = {"stationary": {}, "constant_velocity": {}}
    for lead in range(1, MAX_LEAD + 1):
        lead_key = f"lead_{lead:02d}"
        acc = {bl: [] for bl in results}
        for bid in test_bergs:
            recs = by_berg.get(bid, [])
            for j in range(len(recs) - lead):
                r0 = recs[j]
                rt = recs[j + lead]
                p0 = (r0["lat"], r0["lon"])
                true_pos = (rt["lat"], rt["lon"])
                # stationary
                pred_s = stationary(p0)
                # constant velocity
                if j > 0:
                    prev = recs[j-1]
                    v = (r0["lat"] - prev["lat"], r0["lon"] - prev["lon"])
                    pred_cv = constant_velocity(p0, v, lead)
                else:
                    pred_cv = stationary(p0)

                def pos_err_km(a, b):
                    dlat = (a[0]-b[0]) * 111.0
                    dlon = (a[1]-b[1]) * 111.0 * abs(np.cos(np.radians((a[0]+b[0])/2)))
                    return np.sqrt(dlat**2 + dlon**2)

                acc["stationary"].append(pos_err_km(pred_s, true_pos))
                acc["constant_velocity"].append(pos_err_km(pred_cv, true_pos))

        for bl in results:
            v = np.array(acc[bl])
            if len(v) == 0:
                results[bl][lead_key] = {"n": 0}
                continue
            ci = bootstrap_ci(v)
            results[bl][lead_key] = {
                "mae_km": round(float(np.mean(v)), 3),
                "rmse_km": round(float(np.sqrt(np.mean(v**2))), 3),
                "ci_95_km": [round(ci[0], 3), round(ci[1], 3)],
                "n": len(v),
            }

    # Skill: constant_velocity vs stationary
    skill = {}
    for lead in range(1, MAX_LEAD + 1):
        lead_key = f"lead_{lead:02d}"
        s = results["stationary"][lead_key]
        cv = results["constant_velocity"][lead_key]
        if s.get("n", 0) > 0 and cv.get("n", 0) > 0:
            skill[lead_key] = round(skill_vs(s["mae_km"], cv["mae_km"]), 5)
        else:
            skill[lead_key] = None

    return results, skill

berg_results, berg_skill = run_berg_eval()

# ── Assemble output ────────────────────────────────────────────────────────────
print("Writing results …")
output = {
    "status": metadata_status,
    "disclaimer": (
        "These metrics were computed on a FIXTURE_SYNTHETIC dataset, "
        "not on real observational data.  They verify that the evaluation "
        "harness is correct and that all baselines are implemented; they do "
        "NOT constitute real-world skill claims.  Replace with real OSI SAF "
        "or equivalent data when available — see DATA_LINEAGE.md."
    ),
    "split": {
        "train": [split.train[0].isoformat(), split.train[1].isoformat()],
        "val":   [split.val[0].isoformat(),   split.val[1].isoformat()],
        "test":  [split.test[0].isoformat(),  split.test[1].isoformat()],
        "gap_days": MAX_LEAD,
        "leakage_checked": True,
    },
    "berg_split": {
        "train": berg_split["train"],
        "val":   berg_split["val"],
        "test":  berg_split["test"],
    },
    "sea_ice": {
        "baselines": seaice_results,
        "skill_vs_persistence": skill_results,
    },
    "icebergs": {
        "baselines": berg_results,
        "skill_cv_vs_stationary": berg_skill,
    },
    "generated_by": "scripts/run_baselines.py",
}

OUT_FILE.write_text(json.dumps(output, indent=2))
print(f"Wrote {OUT_FILE}")
print("Phase 4 baseline evaluation complete.")
