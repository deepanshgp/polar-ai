"""
Build the fixture harmonised dataset for Phase 4 baseline evaluation.

DATA STATUS: FIXTURE_SYNTHETIC
This script generates a synthetic sea-ice concentration field and iceberg
trajectory dataset derived deterministically from the demo grid layout
(data/demo/sea_ice_daily.jsonl) plus a parameterised seasonal cycle.

WHY SYNTHETIC:
  - Real OSI SAF Level-3 EASE2/Polar-Stereographic files were not obtained in
    Phase 2 (remote download endpoints returned 404; see DATA_LINEAGE.md §2).
  - The Copernicus Marine Service client is not installed in the container.
  - The demo JSONL contains only 5 snapshot dates — insufficient for temporal
    splits and baseline evaluation.

WHAT THIS PRODUCES:
  data/processed/harmonised.npz  — arrays keyed as follows:
    dates       : (T,)  ISO-date strings, one per day (UTC)
    concentration : (T, H, W)  float32 SIC in [0, 1]; NaN on land
    land_mask   : (H, W)  bool, True = land
    lats        : (H,)  grid-row latitudes  (degrees)
    lons        : (W,)  grid-col longitudes (degrees)
    berg_records : JSON-encoded list of iceberg dicts

  data/processed/fixture_metadata.json — provenance record

HONEST LIMIT:
  Because the concentration field is synthetic the numbers in
  results/baselines.json are baseline-vs-baseline comparisons on a fixture;
  they do not measure skill against real nature.  docs/EVALUATION.md says so
  explicitly.  No fabricated "skill claim" is made.

REPRODUCIBILITY:
  Seed 0.  All arrays are fully deterministic from the code below.
"""

import json
import sys
import numpy as np
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parents[1]
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_NPZ = OUT_DIR / "harmonised.npz"
OUT_META = OUT_DIR / "fixture_metadata.json"

# ── 1. Grid definition ────────────────────────────────────────────────────────
# Match the demo JSONL grid: 30 latitude rows × 36 longitude columns
LATS = np.linspace(-80.0, -55.0, 30)   # southern-most first
LONS = np.linspace(-180.0, 180.0, 36, endpoint=False)
H, W = len(LATS), len(LONS)

# Land mask: flag grid cells poleward of -79° and equatorward of -56° as ocean.
# A simple annular mask — no real coastline, clearly synthetic.
LAT_GRID = LATS[:, None] * np.ones((1, W))
LAND_MASK = (LAT_GRID > -56.5) | (LAT_GRID < -79.5)  # True = land

# ── 2. Seasonal SIC model ─────────────────────────────────────────────────────
# Use a simple cosine cycle:
#   SIC(t, lat) = base(lat) + amp(lat) * cos(2π(doy - peak_doy) / 365)
# Parameters tuned so that Antarctic pack ice peaks ~September (doy≈250) and
# retreats to minimum ~February (doy≈45).  Values chosen to produce all four
# regimes (open/mizt/pack/consolidated) across the latitudinal gradient.

PEAK_DOY = 250
LAT_NORM = (LATS - (-80.0)) / 25.0          # 0 = -80°, 1 = -55°

# Base SIC increases toward the pole
BASE = 0.6 - 0.55 * LAT_NORM                 # −80° → 0.6, −55° → 0.05
# Amplitude of seasonal cycle
AMP  = 0.25 + 0.15 * (1 - LAT_NORM)          # larger amplitude poleward

def sic_at_doy(doy: int, rng: np.random.Generator) -> np.ndarray:
    """Return a (H, W) SIC array for a given day-of-year."""
    cycle = np.cos(2 * np.pi * (doy - PEAK_DOY) / 365.25)
    field = BASE[:, None] + AMP[:, None] * cycle       # (H, W)
    # Add small spatial+temporal noise (std 0.05)
    noise = rng.normal(0, 0.05, (H, W))
    field = field + noise
    field = np.clip(field, 0.0, 1.0).astype(np.float32)
    field[LAND_MASK] = np.nan
    return field

# ── 3. Date range: 2 years of daily steps ─────────────────────────────────────
START = date(2024, 1, 1)
END   = date(2025, 12, 31)
all_dates = []
d = START
while d <= END:
    all_dates.append(d)
    d += timedelta(days=1)
T = len(all_dates)

# ── 4. Build concentration cube ────────────────────────────────────────────────
print(f"Building concentration cube: {T} days × {H} lats × {W} lons …")
rng = np.random.default_rng(0)
concentration = np.zeros((T, H, W), dtype=np.float32)
for i, dt in enumerate(all_dates):
    doy = dt.timetuple().tm_yday
    concentration[i] = sic_at_doy(doy, rng)

# ── 5. Iceberg trajectories ────────────────────────────────────────────────────
# Generate 8 synthetic icebergs drifting at constant velocity with wind noise.
# Clearly labelled FIXTURE_SYNTHETIC.
def make_berg(berg_id: str, lat0: float, lon0: float,
              dlat: float, dlon: float, rng: np.random.Generator):
    records = []
    lat, lon = lat0, lon0
    for dt in all_dates:
        records.append({
            "berg_id": berg_id,
            "date": dt.isoformat(),
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "source": "FIXTURE_SYNTHETIC",
        })
        lat += dlat + rng.normal(0, 0.01)
        lon += dlon + rng.normal(0, 0.015)
        lat = max(-80.0, min(-55.0, lat))
        lon = ((lon + 180) % 360) - 180
    return records

berg_seeds = [
    ("FX-01", -67.0, -52.0,  0.008,  0.03),
    ("FX-02", -70.0, -45.0,  0.005, -0.04),
    ("FX-03", -65.0, -30.0,  0.012,  0.02),
    ("FX-04", -72.0,  10.0,  0.006,  0.05),
    ("FX-05", -68.0,  60.0,  0.009, -0.03),
    ("FX-06", -75.0, 100.0,  0.004,  0.04),
    ("FX-07", -63.0, 150.0,  0.011,  0.02),
    ("FX-08", -69.0,-120.0,  0.007, -0.05),
]

berg_rng = np.random.default_rng(1)
berg_records = []
for args in berg_seeds:
    berg_records.extend(make_berg(*args, rng=berg_rng))

# ── 6. Save ────────────────────────────────────────────────────────────────────
print(f"Saving to {OUT_NPZ} …")
np.savez_compressed(
    OUT_NPZ,
    dates=np.array([d.isoformat() for d in all_dates]),
    concentration=concentration,
    land_mask=LAND_MASK,
    lats=LATS.astype(np.float32),
    lons=LONS.astype(np.float32),
    berg_records=np.array(json.dumps(berg_records)),
)

metadata = {
    "status": "FIXTURE_SYNTHETIC",
    "disclaimer": (
        "Synthetic fixture dataset generated deterministically from a "
        "parameterised seasonal SIC model.  Not real observational data.  "
        "Baseline metrics computed on this fixture measure algorithm "
        "correctness, not real-world skill."
    ),
    "generated_by": "scripts/build_fixture_dataset.py",
    "seed": 0,
    "date_range": [START.isoformat(), END.isoformat()],
    "grid": {
        "H": H, "W": W,
        "lat_min": float(LATS[0]), "lat_max": float(LATS[-1]),
        "lon_min": float(LONS[0]), "lon_max": float(LONS[-1]),
    },
    "n_days": T,
    "n_bergs": len(berg_seeds),
}
OUT_META.write_text(json.dumps(metadata, indent=2))
print(f"Metadata saved to {OUT_META}")
print("Done.")
