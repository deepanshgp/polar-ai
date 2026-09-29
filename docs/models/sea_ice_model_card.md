# Sea-Ice Forecaster — Model Card

> **Status: NO_MODEL_TRAINED**
> No trained artifact exists. Training requires a verified real harmonised dataset.
> See `docs/DATA_LINEAGE.md` §Phase 4 and `docs/DECISIONS.md` §Phase 5.

---

## Intended use

Decision-support information for Antarctic maritime operations.  Provides
7-day sea-ice concentration fields with per-cell uncertainty estimates,
stratified by ice regime (open/MIZT/pack/consolidated).

This system is **decision-support only** — it is not a certified operational
forecast and must not be the sole basis for routing or safety decisions.

## Explicitly NOT intended for

- Arctic operations (training data is Antarctic; performance in the Arctic
  is entirely unmeasured).
- Operational safety-of-life decisions without cross-referencing official
  national ice services.
- Leads beyond `max_validated_lead` — the API refuses these.
- Any lead before real-data evaluation is complete (current state).

---

## Architecture

### Model 1 — `SeaIcePixelForecaster` (`app/ml/seaice_pixel.py`)

Per-pixel `HistGradientBoostingRegressor`, one per lead (1–7 days).
Predicts the **change from persistence** per lead, per ocean pixel.

**Features per pixel:**
| Feature | Description |
|---------|-------------|
| `sic[t]`, `sic[t-1]`, `sic[t-2]`, `sic[t-3]`, `sic[t-6]` | 5-lag local SIC history |
| `neigh_mean[t]` | 3×3 neighbourhood mean at issue time |
| `wind_u[t]`, `wind_v[t]` | Zonal/meridional wind (0 if missing) |
| `temp2m[t]` | 2m temperature (0 if missing) |
| `sin(2π doy/365)`, `cos(2π doy/365)` | Seasonal encoding |

**Output:** predicted `sic[t+lead] - sic[t]`; final SIC = persistence + delta,
clamped to [0, 1]; land cells = NaN.

**Handles NaN natively** via `HistGradientBoostingRegressor`.

### Model 2 — `SeaIceUNet` (`app/ml/seaice_unet.py`)

Direct multi-horizon U-Net; outputs `[L, H, W]` residuals over persistence.

**Input:** `[T_in × C_dyn + S_static + 2, H, W]` = `[10, H, W]` at default.
**Output:** `[L, H, W]` residual; add to persistence then clamp.

**Training details:**
- Loss: masked Huber, MIZT weight ×3, edge-band weight ×2.
- Early stopping on validation skill vs persistence in MIZT at median lead.
- Patience: 10 epochs (5-epoch eval interval).
- Dropout in bottleneck.
- Fixed seeds (reproducible).

---

## Training data and period

*(To be filled when training completes on real data.)*

| Field | Value |
|-------|-------|
| Source | OSI SAF Level-3 sea-ice concentration (product OSI-401-b or OSI-450) |
| Date range | TBD |
| Grid | TBD (native OSI SAF projection, EPSG:3031 intended) |
| Training split | 70% train / 15% val / 15% test, **chronological, 7-day gap** |
| Leakage check | `assert_no_leakage(split, max_lead=7)` passes before any training |
| Forcing | ERA5 wind + 2m temperature (bilinear regrid to analysis grid) |
| Land mask | OSI SAF land/status flag |

---

## Evaluation methodology

*(Numbers to be filled from `results/seaice_eval.json` by `scripts/train_sea_ice.py`.)*

- Test block is touched **exactly once**.
- Metrics: MAE, RMSE, IIEE (flat-Earth cell areas), skill vs persistence,
  skill vs damped persistence; bootstrap 95% CI (n=1000).
- Stratification: by regime (open / MIZT / pack / consolidated) and season (DJF/MAM/JJA/SON).
- Serving decision per §7.6 — written to `config/serving.yaml`.

| Lead | Served model | MIZT MAE | Skill vs persistence | IIEE (km²) | n |
|------|-------------|----------|----------------------|------------|---|
| 1 | TBD | — | — | — | — |
| 2 | TBD | — | — | — | — |
| 3 | TBD | — | — | — | — |
| 4 | TBD | — | — | — | — |
| 5 | TBD | — | — | — | — |
| 6 | TBD | — | — | — | — |
| 7 | TBD | — | — | — | — |

---

## Known failure modes and mitigations

| Failure mode | Check | Mitigation |
|---|---|---|
| Output outside [0, 1] | Asserted; clamp applied | Final `np.clip` + assertion in smoke test |
| Open-water error exceeds persistence | Checked per regime in eval | Report; serve persistence if so |
| Land cells not NaN | Checked in unit tests | Land mask applied at output |
| Non-finite loss | Detected, logged, halted | `torch.isfinite(loss)` check with early exit |
| Seasonal bias | Season breakdown in eval | Report per-season skill; do not tune on test |
| Ice-edge smoothing | IIEE reported | Edge-band upweighted in loss |

---

## Reproducibility

```bash
# 1. Obtain real harmonised dataset
# 2. Verify data/processed/fixture_metadata.json status != FIXTURE_SYNTHETIC
python scripts/train_sea_ice.py --seed 0
# Writes: results/seaice_eval.json, config/serving.yaml, models/manifest.json
```

---

## Current status

> [!WARNING]
> **No model has been trained.** `config/serving.yaml` shows `status: NO_MODEL_TRAINED`
> and `max_validated_lead: 0`. The API returns `data_mode: unavailable` for all
> forecast leads until training completes on real data.
>
> The blocking prerequisite is a verified real harmonised dataset — see
> `docs/DATA_LINEAGE.md` §"Path to real data".

---

*This card follows the §17.2 template from `SIH26059_Documentation.md`.*
