# SIH 26059 — Migration Plan: POLAR-AI Demo → Documented System

*A companion to `SIH26059_Documentation.md`. This document does not repeat that plan; it maps the existing `polar-ai-main` repository onto it and sequences the changes needed to close the gap.*

---

# 0. What This Document Is

You already have a working full-stack application: `polar-ai-main`. It has a FastAPI backend with 15 routers, SQLAlchemy models for icebergs, sea ice, ocean, weather, routes and vessels, a React/TypeScript frontend with 8 pages and a map, Docker packaging, and 33 passing tests.

It is not the system described in `SIH26059_Documentation.md`, for reasons detailed in the analysis that preceded this document: every dataset is synthetic, the reported skill scores measure a model recovering a smooth formula rather than forecasting real ice, the trained model is never loaded by the serving code, the iceberg drift model is a fabricated formula, and the router runs on the synthetic field with no hard-constraint safety behaviour.

This document is **not a rewrite-from-scratch plan.** It is a migration: keep what is structurally sound (the API shape, the database schema, the frontend shell, the Docker setup), and replace what is not (every data source, the model, the risk table, the router's constraints, and every number in the documentation). Each phase names the exact files in the existing repository being replaced or extended.

**No deadline is assumed in this document.** Phases are sequenced by dependency, not by calendar time. Do them in order; do not skip the verification steps to move faster.

---

# 1. Repository Reconnaissance (what exists today)

This section is the map every later phase refers back to. It was produced by reading the repository directly, not by inference.

## 1.1 Backend routers (`backend/app/routers/`, mounted in `main.py`)

| Router | Prefix | Keep, replace internals, or remove |
| ----- | ----- | ----- |
| `health.py`, `system.py` | `/api` | Keep, extend (§7) |
| `dashboard.py` | `/api` | Keep, rewire to real data |
| `sea_ice.py` | `/api/sea-ice` | Keep endpoints, replace `sea_ice_service.py` internals entirely |
| `icebergs.py` | `/api/icebergs` | Keep endpoints, replace `iceberg_service.py` internals entirely |
| `weather.py` | `/api/weather` | Keep, replace `weather_service.py` internals |
| `ocean.py` | `/api/ocean` | Keep, replace `ocean_service.py` internals |
| `routes.py` | `/api` | Keep endpoint shape, replace `route_service.py` entirely (new planner) |
| `analytics.py` | `/api` | Keep, rewire to real evaluation results |
| `data_sources.py` | `/api` | Keep, extend to report the new provenance model |
| `agent.py` | `/api/agent` | Keep, rewrite tool implementations (§9) |
| `simulation.py` | `/api/simulation` | **Rename in spirit or remove** — see §9.4 |
| `satellite.py`, `vessel.py`, `alerts.py` | `/api` | Review case by case in Phase 7; not core to the documented system |

## 1.2 Database models (`backend/app/models/`)

| File | Table(s) | Verdict |
| ----- | ----- | ----- |
| `sea_ice.py` | `sea_ice_observations`, `sea_ice_forecasts` | Reusable schema; needs columns for provenance, regime, and model_id (§4) |
| `icebergs.py` | `icebergs`, `iceberg_positions`, `iceberg_trajectory_predictions` | Reusable; needs a `source` distinction between historical training data and live positions |
| `ocean.py`, `weather.py` | `ocean_observations`, `weather_observations` | Reusable as-is for storing regridded arrays or point samples |
| `routes.py` | `routes`, `route_points`, `risk_assessments` | Reusable; `risk_assessments` needs to store the real risk-table version used |
| `vessels.py` | `vessels` (has `ice_class`) | **This is a good sign** — ice-class awareness is already modelled. Populate `ice_class` from the real standard (§6) |
| `base.py` | `system_events` | Reusable for audit/logging |

## 1.3 What must be built new, not adapted

* `app/sources/*.py` currently fetch NSIDC monthly extent and the NIC iceberg CSV only, and fall back silently to `demo_service` on any exception. These need to become the full ingestion layer from the documentation (§4 of the Implementation Plan document): OSI SAF concentration, ERA5 wind and temperature, Copernicus Marine currents, and the BYU historical iceberg database, each with the checks in that document's §4.6.
* `app/services/demo_service.py` (623 lines) is the synthetic-data engine that every other service silently falls back to. It must stop being a silent fallback (§3).
* `app/ml/sea_ice_model.py` and `train_sea_ice.py` train on synthetic features and are never loaded by any service. These are replaced by the real training pipeline.
* `app/services/route_service.py`'s A* runs on the synthetic field with a single hard threshold (`sic > 0.90 → impassable`) and no ice-class awareness, no iceberg buffers, and no refusal behaviour. This is rebuilt per the documentation's routing section.
* `MODEL_EVALUATION.md` and the skill-score claims in `README.md` must be regenerated from real evaluation runs or deleted until they exist.

## 1.4 Explicit non-goals of this migration

* Do not attempt to preserve the "autonomous dynamic replanning" demo framing from `simulation_service.py`. It conflicts with the decision-support-only principle.
* Do not preserve any number currently in `MODEL_EVALUATION.md`. Every number there was produced on synthetic data with a leaking evaluation and must be recomputed or removed.
* Do not keep silent fallback to demo data in any user-facing response once Phase 3 is complete. `data_mode` must always be explicit and visible.

---

# 2. Sequencing and Dependencies

```
Phase 0  Repository triage and safety net (tag, branch, freeze)
Phase 1  Provenance and data-mode integrity (kill silent fallback)
Phase 2  Real ingestion layer (replaces app/sources/*)
Phase 3  Analysis grid, harmonisation, and the DB schema migration
Phase 4  Splits, baselines, and the evaluation harness
Phase 5  Sea-ice forecaster (replaces app/ml/*)
Phase 6  Iceberg drift model (replaces the drift formula in demo_service.py)
Phase 7  Ice-risk engine and fuel estimator (new modules)
Phase 8  Route planner rebuild (replaces route_service.py)
Phase 9  API integration (rewire routers and services)
Phase 10 Frontend integration (map layers, status, uncertainty, refusal states)
Phase 11 Agent/tools rewrite (replaces agent/tools.py internals)
Phase 12 Documentation, verification script, and final honesty pass
```

Each phase's prompt in Part 2 of this document names the exact files it touches. Phases 5 through 8 can run in parallel across a team once Phase 3 is complete, since they depend on the harmonised data and evaluation harness but not on each other. Phase 9 depends on all of 5 through 8.

---

# Migration Build Prompts

*Part 2: Copy-paste prompts for a coding agent, in sequence. Each prompt names the exact existing files it replaces or extends, and refers to `SIH26059_Documentation.md` for algorithms and interfaces already specified there rather than repeating them.*

**Standing instruction (paste once before Phase 0):**

> You are migrating the repository `polar-ai-main` from a synthetic-data demo into the system specified in `SIH26059_Documentation.md` (Parts 1 and 2 of that file are the architecture and implementation plan; treat them as authoritative for algorithms, interfaces, and non-negotiable principles). This migration document (`MIGRATION_PLAN.md`) tells you which existing file maps to which part of that specification. Work phase by phase, in order. Before changing a file, read it in full. Prefer extending existing routers, schemas, and database models over replacing them, unless a phase explicitly says to replace something. After each phase, run the existing test suite (`backend/tests/test_api.py`) plus any new tests the phase adds, and fix failures before moving on. The non-negotiable principles from the documentation apply throughout: never fabricate data or substitute a default silently — return an explicit `unavailable`/`is_real: false` marker instead; use time-based splits only, never random; assert and record units and provenance; every forecast carries an uncertainty object; the route planner never violates a hard constraint, including after smoothing; every reported number must trace to a script and a result file, never be hand-typed into a README; do not present the tool as autonomous. If you must deviate from either document, record the deviation and reason in `docs/DECISIONS.md`. Do not invent dataset variable names, product IDs, or table values — read them from real files or cite the real published source.

---

## Phase 0 — Repository Triage and Safety Net

**Goal:** Before changing anything, freeze a known-good state of the demo, and give yourself a place to fall back to if a migration step goes wrong. This costs almost nothing and prevents the most common failure mode in a migration: ending up with a broken app and no working demo to present while the real one is unfinished.

**Prompt:**

> In the `polar-ai-main` repository:
> 1. Create a git tag `demo-v1-synthetic` at the current commit, and push it. This is the last commit where the synthetic demo is fully working end to end. Do not delete or rewrite this tag.
> 2. Create a branch `migration/real-data` from the current commit and do all migration work on it, merging to `main` only at agreed checkpoints (for example, after Phase 4, Phase 8, and Phase 12).
> 3. Run the existing test suite (`cd backend && pytest tests/test_api.py -v`) and confirm the baseline is 33 passing, per the README. Record the exact output in `docs/MIGRATION_LOG.md` as the starting point.
> 4. Run the app once via `docker compose up --build` in demo mode and take screenshots of all 8 frontend pages. Save them to `docs/screens/demo-v1/`. These become the "before" record for the final comparison in Phase 12, and a fallback demo if a later phase is incomplete when you need to show something.
> 5. Read `README.md`, `PROJECT_PLAN.md`, `DATA_SOURCES.md`, and `MODEL_EVALUATION.md` in full and list, in `docs/MIGRATION_LOG.md`, every specific numeric claim in them (for example the skill scores, the iceberg position errors, the route distances). This list is what Phase 12 must either reproduce honestly or remove.
> 6. Create `docs/DECISIONS.md` and `docs/DATA_LINEAGE.md` now, empty except for headers, per the structure in `SIH26059_Documentation.md` Implementation Plan §2 and §17.

> **Exit criteria.** A tagged, working synthetic demo exists and is not touched again except to reference it. A migration branch exists. The starting test count and the list of claims to resolve are recorded. Commit as "Phase 0: migration safety net and claim inventory."

---

## Phase 1 — Kill Silent Fallback; Make Data Mode Explicit Everywhere

**Goal:** The single most important structural problem in the current codebase is that every service silently falls back to `demo_service` on any exception (`_get_real_icebergs`, `_use_real` in `sea_ice_service.py` and `iceberg_service.py` follow this pattern) and the frontend cannot always tell the difference. Fix this pattern once, everywhere, before building any real data source, so that every subsequent phase is honest by construction rather than by discipline.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §3.3 (`Provenance`) and §1.2 (`Never fabricate`):

> 1. In `backend/app/core/`, add `provenance.py` implementing the `Provenance` dataclass from the documentation (source, product_id, variable, units, valid_time, retrieved_at, resolution_m, native_grid, notes). This sits alongside the existing `freshness.py`, which already tracks a `FreshnessRegistry` — read that file first and decide whether `Provenance` subsumes it or wraps it; record the decision in `docs/DECISIONS.md`.
> 2. Grep the codebase for every occurrence of the pattern `try: ... real ... except Exception: pass` that results in a silent fallback (this pattern appears in at least `sea_ice_service.py`, `iceberg_service.py`, `ocean_service.py`, `weather_service.py`). For each one, change the behaviour so that a failure to reach or parse a real source produces a typed result carrying `is_real: false`, `data_mode: "demo"` or `data_mode: "unavailable"` (do not conflate "using demo data" with "the real source is broken" — these are different states and the frontend must be able to show a different message for each), and a `reason` string. Never let an exception silently and invisibly select demo data.
> 3. Introduce a project-wide `data_mode` enum with exactly three values used consistently everywhere: `real` (from a live or archival source), `demo` (explicitly synthetic, for development only), `unavailable` (a real source was expected but could not be reached or validated). Audit every API response schema in `backend/app/schemas/` and add this field where missing.
> 4. In the frontend, audit `DemoBanner.tsx`, `FreshnessTag.tsx`, and `SystemStatusBar.tsx` (these already exist and are a good foundation) and confirm each of the three `data_mode` values renders visibly differently. `unavailable` must look alarming, not like a quieter version of `demo`.
> 5. Add a test in `backend/tests/test_api.py` (or a new `test_data_mode.py`) that simulates a real source raising an exception and asserts the API response is `data_mode: "unavailable"` with a reason, not a silent switch to demo values.
> 6. Do not implement any new real data source in this phase. This phase is purely about making the existing true/false distinction explicit and impossible to hide.

> **Exit criteria.** No code path silently substitutes demo data without marking it. The three-state `data_mode` is used consistently in schemas and the frontend. The new test passes. Commit as "Phase 1: explicit data-mode and provenance, remove silent fallback."

---

## Phase 2 — Real Ingestion Layer

**Goal:** Replace `app/sources/*.py`'s narrow, single-purpose fetchers with the full ingestion layer specified in `SIH26059_Documentation.md` Implementation Plan §4, while keeping the existing NSIDC and NIC fetchers as the starting point rather than discarding them.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §4 (Ingestion Layer) and Part 1 §4 (Data Program):

> 1. Read `app/sources/sea_ice_source.py` and `app/sources/iceberg_source.py` in full. These already implement real HTTP fetches (NSIDC `G02135` monthly/daily extent, and the NIC iceberg CSV) with `is_configured()` checks. Keep their HTTP and parsing logic as a starting point, but they currently only fetch **extent summaries** and **live iceberg positions** — neither is sufficient for the documented system, which needs the **gridded** OSI SAF concentration product and the **historical** BYU iceberg database for training.
> 2. Add `backend/app/sources/osisaf_source.py` implementing `fetch`, `load`, `validate` for the Copernicus Marine OSI SAF sea-ice concentration product, per the documentation's §4.2. Convert to a 0–1 fraction, mask flagged and land cells, and attach a `Provenance`.
> 3. Add `backend/app/sources/era5_source.py` for 10 m wind and 2 m temperature, per §4.3, including the vector-rotation requirement — implement `rotate_to_grid` now even though the analysis grid is finalised in Phase 3, and write its unit test against hand-computed cases at several longitudes as the documentation specifies.
> 4. Add `backend/app/sources/currents_source.py` for Copernicus Marine surface currents, per §4.4, with the same vector-rotation requirement.
> 5. Extend `iceberg_source.py` (or add `iceberg_historical_source.py`) to also load the BYU consolidated historical database, distinct from the existing live-list fetch. Normalise both into the schema in §4.5 (`berg_id, timestamp, lon, lat, source_sensor, quality_flag`), preserving the distinction between historical (training) and live (serving) records — this maps onto the existing `IcebergPosition` model in `app/models/icebergs.py`, which should gain a `source_kind` column (`historical` vs `live`).
> 6. Implement `app/core/checks.py` (new) with the validation functions from §4.6, and run them from every source's `validate()` method. A build step (a new `scripts/verify_datasets.py` at the repo root, mirroring the one in the documentation) must run all sources' `validate()` and fail on any error-level finding.
> 7. Update `.env.example` and `DATA_SOURCES.md` with the credential and account requirements for OSI SAF/Copernicus Marine, CDS/ERA5, and confirm the existing NSIDC and NIC entries are still accurate.
> 8. Do not build the harmonisation (regridding/alignment) layer yet — that is Phase 3. This phase only proves each source can be fetched, parsed, validated, and provenance-tagged in isolation.
> 9. Create small fixture files from real downloads (a few days, a small crop) under `backend/tests/fixtures/`, as the documentation's §0 recommends, for fast tests in later phases.

> **Exit criteria.** `scripts/verify_datasets.py` runs cleanly against all five sources (NSIDC, NIC live, BYU historical, OSI SAF, ERA5, Copernicus Marine currents — six, correcting the count) and reports real grid, units, and date ranges into `docs/DATA_LINEAGE.md`. Vector rotation is unit-tested against hand-computed values. Fixtures exist for later tests. Commit as "Phase 2: real ingestion layer for sea ice, wind, currents, and historical icebergs."

---

## Phase 3 — Analysis Grid, Harmonisation, and Schema Migration

**Goal:** Define the one shared grid every model and the database will use, build the regridding/alignment layer, and migrate the existing Alembic schema to carry provenance and grid references instead of the current free-floating lat/lon point samples.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §3 (Configuration and Grid) and §5 (Harmonisation):

> 1. Add `backend/app/core/grid.py` implementing `AnalysisGrid` exactly as specified in §3.2, and `config/domain.yaml` per §3.1. Choose the projection to match the OSI SAF product's native grid (confirm the exact EPSG or PROJ string from the files fetched in Phase 2 — do not assume one). Write the round-trip and cell-area tests specified there.
> 2. Add `backend/app/harmonise/regrid.py` and `align.py` per §5.1 and §5.2, regridding ERA5 and current data onto the analysis grid and aligning all sources to a shared daily UTC time axis. Test regridding against an analytic field as specified.
> 3. Review the existing Alembic migrations `001_initial_schema.py` and `002_real_data_tables.py`. Decide, and record in `docs/DECISIONS.md`, whether the existing point-sample schema (`SeaIceObservation`, `OceanObservation`, `WeatherObservation` with individual `lat`/`lon` columns) is adequate for storing harmonised gridded arrays, or whether gridded data should instead live in files (NetCDF/Zarr) referenced by path and metadata from the database, with the database holding only summaries, forecasts, and provenance. Given that PostGIS is already a dependency, storing full daily grids as rows is likely to become unwieldy — lean toward the file-plus-metadata approach unless the existing schema is a clear fit, but justify the choice either way.
> 4. Write a new Alembic migration `003_provenance_and_grid.py` adding the columns needed for your Phase 3.3 decision: at minimum, a `provenance` JSON column and a `model_id`/`model_hash` column on `SeaIceForecast` and `IcebergTrajectoryPrediction`, and a `source_kind` column on `IcebergPosition` (from Phase 2). Do not silently drop the existing tables; write the migration to be additive and reversible.
> 5. Implement `harmonise/dataset_builder.py` per §5.3, producing the model-ready tensor shapes specified there, backed by the fixtures from Phase 2.
> 6. Update `docs/DATA_LINEAGE.md` with the finalised grid definition, the regridding method per variable, and the aggregation rule from sub-daily to daily.

> **Exit criteria.** `AnalysisGrid` tests pass, including the dateline round-trip. The schema decision is recorded and the new migration applies cleanly on top of the existing two. `dataset_builder` produces correctly shaped tensors from the fixtures. Commit as "Phase 3: analysis grid, harmonisation, and schema migration."

---

## Phase 4 — Splits, Baselines, and the Evaluation Harness

**Goal:** Build the yardstick that will replace the leaking, synthetic-formula "evaluation" currently in `train_sea_ice.py` and `MODEL_EVALUATION.md`. This is the phase that makes every later number trustworthy.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §6 in full. This phase is almost entirely new code, since nothing in the existing repository does this correctly today — `train_sea_ice.py`'s `train_test_split(..., random_state=42)` is a random split on synthetic, spatially-and-temporally-correlated data, which is exactly the leakage pattern this phase exists to prevent.

> 1. Implement `backend/app/evaluation/splits.py` (`make_time_split`, `assert_no_leakage`, `make_berg_split`) per §6.1. Write the leakage test that fails on a deliberately leaky split.
> 2. Implement `backend/app/evaluation/seaice_baselines.py` (persistence, climatology from training data only, damped persistence) and `iceberg_baselines.py` (stationary, constant-velocity, physics-only) per §6.2 and §6.3.
> 3. Implement `backend/app/evaluation/metrics.py` (MAE, RMSE, skill score, IIEE using the `AnalysisGrid`'s cell areas, position error, bootstrap confidence intervals) and `regimes.py` (stratification by ice regime, defined from the forecast-issue-time field) per §6.4 and §6.5.
> 4. Write `scripts/run_baselines.py` that runs end to end on real, harmonised data (from Phase 3) and writes `results/baselines.json` with every baseline, at every lead, in every regime, with sample counts and seasonal breakdowns — the direct replacement for the fabricated numbers in `MODEL_EVALUATION.md`.
> 5. Compare the new `results/baselines.json` against the claims inventory from Phase 0's `docs/MIGRATION_LOG.md`. Write a short note in `docs/EVALUATION.md` stating plainly which old claims (the 0.81/0.83/0.81 skill scores, the 1.8–52.8 km iceberg errors) do not survive contact with real data and a correct evaluation, and why. This note is a deliverable, not an aside — it is evidence the migration fixed a real problem, and it is the honest replacement content for `MODEL_EVALUATION.md`'s current numbers.
> 6. Do not train any model in this phase.

> **Exit criteria.** The leakage test fails on a leaky split. `results/baselines.json` exists from real data. The comparison note against the old claims is written. Commit as "Phase 4: real evaluation harness, superseding the synthetic baseline numbers."


## Phase 5 — Sea-Ice Forecaster

**Goal:** Replace `app/ml/sea_ice_model.py` and `train_sea_ice.py`, and make the serving code (`sea_ice_service.py`) actually load and use the trained artifact — currently it never does.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §7:

> 1. Read `app/ml/sea_ice_model.py` and `app/ml/train_sea_ice.py` in full. Confirm, as found during the earlier analysis, that no service imports or loads the models these scripts produce (`app/services/sea_ice_service.py` calls `demo_service.get_sea_ice_forecast` unconditionally). This is a real, separate bug from the synthetic-data problem and must be fixed regardless of what model replaces the current one.
> 2. Implement `app/ml/seaice_pixel.py` (per-pixel gradient-boosted baseline, predicting the change from persistence) as specified in §7.2, trained on the real, harmonised, correctly-split data from Phases 3 and 4. Evaluate it with the Phase 4 harness.
> 3. Implement `app/ml/seaice_unet.py` (direct multi-horizon U-Net) per §7.3, with the masked, regime-weighted residual loss, land handling, and training discipline in §7.3–7.4 (fixed seeds, early stopping on validation skill, NaN detection).
> 4. Train both, evaluate on the frozen test block exactly once, and write `results/seaice_eval.json` with the full breakdown (MAE, RMSE, skill vs every baseline, IIEE, sample counts, by regime, lead, and season) as specified in §7.4.
> 5. Apply the outcome rules in §7.6 mechanically. Write the result into a new `config/serving.yaml` (`served_model_by_lead`, `max_validated_lead`). **If the U-Net does not beat persistence at some lead, serve persistence at that lead and say so — this is a legitimate, documented outcome, not a failure to fix by further tuning.**
> 6. Fix `app/services/sea_ice_service.py` to actually load the model registry (implement `app/ml/registry.py` per the documentation's §12.4 — hash verification and a smoke-test round trip) and serve the model or baseline indicated by `serving.yaml` for the requested lead, refusing (HTTP 422, not a silent substitution) for any lead beyond `max_validated_lead`.
> 7. Update `SeaIceForecast` (the existing DB model in `app/models/sea_ice.py`) writes to include `model_id`, `model_hash`, and the uncertainty envelope from `results/seaice_eval.json` for the regime and lead being served.
> 8. Write `docs/models/sea_ice_model_card.md` per the documentation's §17.2.
> 9. Delete or clearly quarantine the old `app/ml/sea_ice_model.py`/`train_sea_ice.py` if they are fully superseded; if any part is reused (for example, a useful preprocessing helper), say so explicitly in `docs/DECISIONS.md` rather than leaving two parallel implementations that could be confused for each other.

> **Exit criteria.** `results/seaice_eval.json` exists from real, correctly-split data. `serving.yaml` reflects the measured outcome per lead, including any lead where persistence is served instead of the learned model. `sea_ice_service.py` actually loads and uses a model. The model card states limits honestly. Commit as "Phase 5: real sea-ice forecaster, actually wired into serving."

---

## Phase 6 — Iceberg Drift Model

**Goal:** Replace the fabricated drift formula in `demo_service._iceberg_drift` (currently used even for real NIC-sourced icebergs, per `iceberg_service.py`'s `_get_real_icebergs` enrichment path) with a physics-anchored model trained on the real historical database from Phase 2.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §8:

> 1. Confirm, as found during analysis, that `app/services/iceberg_service.py` calls `demo_service._iceberg_drift(...)` to compute drift even for **real** NIC icebergs (see `list_icebergs()`'s "enrich real icebergs with computed risk and drift" path). This means every "real" iceberg in the current app still has fabricated movement. This phase must remove every call site that does this, not only the purely-demo path.
> 2. Using the BYU historical database ingested in Phase 2, build the drift training pairs per §8.1: consecutive position pairs per berg with a bounded time gap, projected-coordinate displacement, discard rules for large gaps and implausible speeds, and features sampled from the (now-real, gridded) wind, current, and sea-ice concentration at the start position and time, with vector rotation applied.
> 3. Split with `make_berg_split` from Phase 4 (by berg identity and time). Assert no berg appears in more than one split.
> 4. Implement `app/ml/iceberg_physics.py` (the baseline: current plus fitted wind-drag coefficient) and `app/ml/iceberg_residual.py` (the learned residual on top of it) per §8.3–8.4.
> 5. Implement multi-step forecasting per §8.5 and compute the uncertainty radius per lead from held-out error, replacing the current formula-based uncertainty (`2.0 + h/72.0*25.0` in `iceberg_service.py`'s `_predict_custom`) with the real measured value from `results/iceberg_eval.json`.
> 6. Evaluate against stationary, constant-velocity, and physics-only baselines with bootstrap confidence intervals and sample sizes, per §8.6, and apply the acceptance rule: ship the learned residual only if it beats both baselines with a CI excluding zero, otherwise ship the better baseline and say so.
> 7. Rewire `app/services/iceberg_service.py`: `list_icebergs()`, `get_iceberg_detail()`, `get_trajectory()`, and `predict_trajectory()` must all call the new model (or the winning baseline) instead of `demo_service._iceberg_drift`, for both real and (clearly labelled) demo icebergs. Position history for real bergs (`get_iceberg_detail`'s fabricated `positions` list, currently generated by walking the fake drift function backward in time) must come from actual historical positions in the BYU/NIC data, not a generated backward walk.
> 8. Update `IcebergTrajectoryPrediction` (existing DB model) to store `model_id`, the uncertainty radius, and provenance.
> 9. Write `docs/models/iceberg_model_card.md` per §17.2, explicitly stating the live-feed coverage limitation (a few dozen large bergs, updated weekly) that the current README does not mention.

> **Exit criteria.** No code path computes iceberg movement from the fabricated formula for anything labelled `data_mode: "real"`. `results/iceberg_eval.json` exists with real sample sizes and skill against baselines. Uncertainty radii come from measured error, not a formula. Commit as "Phase 6: real iceberg drift model, fabricated formula removed from all real-data paths."

---

## Phase 7 — Ice-Risk Engine and Fuel Estimator

**Goal:** Replace the ad hoc thresholds in `route_service.py` (`sic > 0.90 → impassable`, fixed breakpoints at 0.70 and 0.40) and the weighted-sum risk in `risk_service.py` with the documented, data-driven, ice-class-aware engine.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §9 and §10:

> 1. Read `app/services/risk_service.py` in full, including the fixed weights (Sea Ice 0.35, Iceberg 0.30, Weather 0.20, Ocean 0.15 — visible in `README.md`'s architecture diagram and `MODEL_EVALUATION.md`'s calibration table). Decide, and record in `docs/DECISIONS.md`, whether this weighted-sum structure is kept as one input to the new engine or replaced outright by the ice-class table lookup in §9.2–9.3. The documentation's approach (a regulatory ice-class table) and the existing weighted-sum approach are not the same thing; do not silently blend them without stating how.
> 2. Source the actual published ice-class risk-index table the documentation refers to (do not reproduce values from memory). Encode it in `config/risk_tables.yaml` as data, per §9.2. If it cannot be obtained, implement against a table explicitly labelled `PLACEHOLDER` everywhere it surfaces (API responses, frontend, README), per the documentation's fallback instruction.
> 3. Implement `app/risk/risk_index.py` (`risk_grid`, `is_passable`, `RiskLevel`) per §9.3, using the real forecast concentration and uncertainty from Phase 5, and the vessel's `ice_class` — note that `app/models/vessels.py` **already has an `ice_class` column** (`"1A", "1B", "PC4", "PC3"`), which is a real asset to build on; populate it meaningfully instead of leaving it a default string.
> 4. Write the property tests in §9.4 (monotonicity in concentration and ice class) using `hypothesis`.
> 5. Implement `app/fuel/fuel_model.py` per §10, replacing the current `ice_penalty = 1 + avg_sic * 0.8` ad hoc formula in `route_service.py` with the documented, parameterised, cited-or-labelled-as-assumption model. Write `docs/ROUTE_COST.md` with a worked example computed by the code.
> 6. Write the fuel property tests (non-decreasing in distance and in ice, non-negative).
> 7. Update `risk_service.py`'s API surface to also expose the new engine's output, and update `RiskAssessment` (existing DB model) to store which risk-table version was used.

> **Exit criteria.** Risk is computed from a cited table or a loudly-labelled placeholder, is ice-class aware using the existing `Vessel.ice_class` field, and passes the monotonicity property tests. Fuel is documented and property-tested. Commit as "Phase 7: data-driven, ice-class-aware risk engine and documented fuel model."

---

## Phase 8 — Route Planner Rebuild

**Goal:** Replace `route_service.py`'s A* — which currently runs on the synthetic field, has no refusal behaviour, no iceberg buffers, and a single hard-coded impassability threshold — with the time-dependent, hard-constraint planner from the documentation.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §11:

> 1. Read `app/services/route_service.py` in full (448 lines). Keep the existing `_haversine_km`, `_snap_to_grid`/`_grid_to_latlon` coordinate helpers and the overall A* control flow as a starting skeleton, but replace: the cost function (`_node_cost`, currently `demo_service._sic_at` plus a fixed iceberg-distance term and a random-seeded fudge factor) with the documented cost grid; the fixed 1° `GRID_STEP` with the shared `AnalysisGrid` from Phase 3 (or an explicitly coarser routing grid derived from it, if full resolution is too slow — measure first per §11.8, don't assume); and the single impassability threshold with the ice-risk engine's `is_passable` from Phase 7.
> 2. Implement `app/routing/cost_grid.py` per §11.1: per-time-slice costs from forecast risk (Phase 5 and 7), iceberg exclusion buffers sized from the Phase 6 uncertainty radius plus a safety margin, the land/shallow mask, and distance — with cost depending on estimated arrival time, not just static state.
> 3. Implement time-dependent A* per §11.2 with the three weight presets (fastest/safest/balanced), replacing the current single-route-type default. Confirm this produces the `RouteOption` shape needed by the existing `compare_routes` endpoint, which the frontend's `RoutePlannerPage.tsx` already expects — check that page's expected response shape before changing the schema, to avoid an unnecessary frontend rewrite.
> 4. Implement `smooth.py` per §11.3, with the mandatory re-check that a smoothed segment never enters an impassable cell.
> 5. Implement `explain.py` per §11.5 — templated, numeric, factual explanations — replacing the current hand-written f-string in `compare_routes` (`f"Average sea-ice concentration along route: {safest['avg_ice_concentration']*100:.0f}%."`) with something that generalises to any route, not just the safest one, and is generated from the same numbers the planner computed rather than assembled ad hoc per call site.
> 6. Implement the typed errors from §11.6 (`DataUnavailable`, `ForecastHorizonExceeded`, `NoPassableRoute`, `StartOrGoalImpassable`, `StaleData`) and wire them to the FastAPI exception handlers in `main.py`, replacing whatever the current behaviour is when, for example, `route_service.py` is asked to route through data that doesn't exist (check this behaviour first — the current code likely returns a route anyway, silently, which is exactly the failure mode the documentation exists to prevent).
> 7. Write the `hypothesis` property tests specified in §11.7/§15: zero hard-constraint violations across randomised ice fields and start/goal pairs, determinism, and correct refusal in each typed-error scenario. This is, per the documentation's risk register, the single most safety-critical test in the whole project — do not under-invest here relative to the ML phases.
> 8. Measure planner runtime on a realistic grid and record it in `results/routing_perf.json`; if too slow for the frontend's interactive use, optimise the search rather than weakening a constraint.
> 9. Update `Route`/`RoutePoint` (existing DB models) to store `beyond_forecast_horizon` and the warnings list.

> **Exit criteria.** The zero-violation property test passes across many random cases. Every typed error is triggered by a test and produces no route. `compare_routes`'s response shape is preserved or the frontend is updated to match, deliberately, not by accident. Commit as "Phase 8: hard-constraint route planner replacing the synthetic-field A*."


## Phase 9 — API Integration and Cross-Cutting Consistency

**Goal:** With every internal engine rebuilt in Phases 5–8, make sure the routers, schemas, and system-status reporting present them consistently, and that nothing still quietly reads from `demo_service` where real data is expected.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §12 and §14:

> 1. Grep the entire `backend/app` directory for remaining references to `demo_service` outside of explicit, clearly-labelled demo-mode code paths. For each one found in `sea_ice_service.py`, `iceberg_service.py`, `ocean_service.py`, `weather_service.py`, `analytics_service.py`, and `dashboard.py` (dashboard likely aggregates from several of these), confirm it is either (a) legitimately gated behind `data_mode == "demo"` for local development without credentials, or (b) a leftover that must now call the real Phase 2–8 code. Fix every case of (b).
> 2. Implement `app/core/registry.py` (model artifact loading with hash verification and smoke test, per §12.4) if not already done in Phase 5, and make sure both the sea-ice and iceberg models go through it.
> 3. Extend `app/routers/system.py` to implement the full `/api/system-status` contract from §12.3: per-component state (`ok`/`degraded`/`unavailable`), newest valid time, age, and reason — covering every ingestion source, both models, the risk engine, and the planner. The existing `health.py` likely covers only basic liveness; keep it, and add the richer status endpoint alongside it.
> 4. Implement freshness-threshold logic consistently (extending the existing `FreshnessRegistry` in `app/core/freshness.py`) so every forecast response includes `stale: true`/`false` and an age, per §12.1.
> 5. Audit every Pydantic response schema in `app/schemas/` for the presence of `provenance` and, for forecasts, an `uncertainty` object. Add a schema test that iterates all forecast-returning endpoints and fails if either is missing, per §15.
> 6. Regenerate `docs/API.md` from real calls against the running service (not hand-written), replacing whatever API documentation currently exists in `README.md`'s endpoint table.
> 7. Run the full existing test suite (`test_api.py`) plus everything added in Phases 1–8, and fix any test that was implicitly asserting synthetic-data behaviour (for example, a test that checks for a specific demo iceberg name or a hard-coded coordinate) so it now asserts against real-data behaviour or fixtures.

> **Exit criteria.** No non-demo-gated code path reads from `demo_service`. `/api/system-status` reports honestly across all components, verified by deliberately breaking one (delete a fixture, corrupt a model hash) and confirming it shows as `degraded`/`unavailable` rather than silently working. Schema test passes. Commit as "Phase 9: API integration, consistent provenance and uncertainty, demo-service audit."

---

## Phase 10 — Frontend Integration

**Goal:** The existing 8-page React app (`DashboardPage`, `SeaIcePage`, `IcebergPage`, `RoutePlannerPage`, `AnalyticsPage`, `NavigatorPage`, `SimulationPage`, `DataSourcesPage`) and its component library (`AntarcticMap`, `RiskGauge`, `FreshnessTag`, `DemoBanner`, `SystemStatusBar`) are a solid shell. Wire them to the rebuilt backend and add the honesty affordances the documentation requires that the current app lacks.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §13:

> 1. Update `frontend/src/services/api.ts` and `frontend/src/types/index.ts` to match the schema changes from Phases 5–9 (provenance, uncertainty, `data_mode` three-state, typed-error responses for routing).
> 2. In `SeaIcePage.tsx`, add the forecast-lead slider behaviour from §13.1: it must not be movable past `max_validated_lead` (read from `/api/system-status` or the forecast response), and must show which model is serving the currently-selected lead (learned model vs. a baseline), per §7.6's outcome table — this is new information the current page doesn't surface and is one of the more important honesty signals in the whole system.
> 3. In `AntarcticMap.tsx`, confirm the existing layer-toggle structure can add wind/current vector layers (documentation §13.1); if not already generic enough, refactor the layer system rather than special-casing each new layer.
> 4. Extend `SystemStatusBar.tsx` and `DataSourcesPage.tsx` to render the richer `/api/system-status` contract from Phase 9 (per-component state, age, reason for degradation), replacing whatever simpler status display currently exists.
> 5. In `RoutePlannerPage.tsx`, handle the new typed-error responses from Phase 8 explicitly: a refused route must show the specific reason (no fabricated route, no generic error toast) and draw nothing on the map. If the risk table is a placeholder (per Phase 7), show a persistent, visible warning on this page specifically, since it's the page whose output is most affected by that table.
> 6. Add an uncertainty display (new `UncertaintyPanel.tsx` component, or extend `RiskGauge.tsx` if that's a better fit given the existing design) showing held-out error by regime for the currently-viewed forecast layer, sourced from `/api/uncertainty`, with the explicit note that this is past error, not a calibrated probability.
> 7. Add or extend a persistent, non-dismissible decision-support banner (check whether `DemoBanner.tsx` can be generalised into this, since it already occupies similar screen real estate, or whether a separate always-on component is clearer — the two messages, "this is demo data" and "this tool does not control the vessel," are different claims and should probably not be visually conflated).
> 8. Decide the fate of `SimulationPage.tsx` and `simulation_service.py`'s "autonomous dynamic replanning" demo (flagged in Phase 0's non-goals). Options, to be decided and recorded in `docs/DECISIONS.md` rather than left ambiguous: remove it; keep it but rename and reframe it as a scripted walkthrough of the real system's behaviour under a hypothetical scenario, with explicit language that no autonomy is involved; or keep it clearly quarantined as a separate, clearly-labelled "demo mode" not part of the evaluated system. Do not leave the current "WOW moment — POLAR-AI autonomous dynamic replanning" framing from `README.md` unaddressed.
> 9. Add frontend tests (extending whatever test setup exists, or adding one with `vitest` if none does) per the documentation's §15: slider cannot exceed the validated lead; an `unavailable` API response renders a message and no fabricated layer; a refused route shows the reason and no path; the decision-support banner cannot be dismissed.
> 10. Take fresh screenshots of all pages and save under `docs/screens/migrated/`, for a direct before/after comparison against Phase 0's `docs/screens/demo-v1/`.

> **Exit criteria.** All frontend tests pass. The four key states (normal, stale, unavailable, refused route) render correctly and were captured in screenshots. The `SimulationPage` decision is made and recorded, not left as-is by default. Commit as "Phase 10: frontend wired to real backend, honesty affordances added."

---

## Phase 11 — Agent and Tools Rewrite

**Goal:** `app/agent/polar_navigator.py` and `app/agent/tools.py` currently query the same services being rebuilt in Phases 5–9, so once those are real, the agent's answers become real too — but its tool descriptions and its rule-based fallback logic may still reference synthetic assumptions and need a direct review.

**Prompt:**

> 1. Read `app/agent/tools.py` (131 lines, 10 tools per the README) and `app/agent/polar_navigator.py` (343 lines) in full.
> 2. For each of the 10 tools, confirm it calls the now-real service functions from Phases 5–9 and correctly surfaces `data_mode`, provenance, and uncertainty in whatever it returns to the LLM or the rule-based fallback — an agent that confidently reports a number without knowing it's `demo`/`unavailable` will produce confidently wrong answers.
> 3. Review the rule-based fallback mode's response templates (used when no LLM API key is set, which the README says "works perfectly without any key") for any hard-coded assumption inherited from the synthetic data (for example, phrasing that assumes a route is always found, or that risk is always one of four clean categories without mentioning a placeholder table).
> 4. Add a test that asks the agent a question when a required backend piece is `unavailable` (for example, the sea-ice forecast) and confirms the agent says so rather than answering as if data were present.
> 5. Update the agent's system prompt or tool descriptions (wherever they currently live in `polar_navigator.py`) to state the decision-support-only framing explicitly, so the agent itself does not inadvertently claim authority it shouldn't.

> **Exit criteria.** All 10 tools surface data_mode/provenance/uncertainty correctly. The unavailable-data test passes. Commit as "Phase 11: agent and tools rewired to real, honestly-labelled data."

---

## Phase 12 — Documentation, Verification Script, and Final Honesty Pass

**Goal:** Bring `README.md`, `MODEL_EVALUATION.md`, `DATA_SOURCES.md`, and `PROJECT_PLAN.md` into agreement with what was actually built, and implement the `verify.py` script so future changes cannot silently drift from the documented numbers again.

**Prompt:**

> Referencing `SIH26059_Documentation.md` Implementation Plan §16 and §17:

> 1. Implement `verify.py` at the repository root per §16: run the fast test suite; load each model artifact and verify its hash and a smoke inference; extract every metric tagged in `README.md` with a machine-readable marker and compare against `results/*.json`, failing on any mismatch; support `--recompute` to re-derive evaluation from checkpoints.
> 2. Rewrite `MODEL_EVALUATION.md` entirely from `results/seaice_eval.json`, `results/iceberg_eval.json`, and `results/routing_perf.json`. Every number must be machine-tagged for `verify.py`. Do not hand-carry forward any number from the old version of this file.
> 3. Rewrite the relevant sections of `README.md`: remove the "Performance on demo data: Skill score 0.81..." claims and replace with the real headline results including any negative outcomes (per §7.6); remove or reframe the "autonomous dynamic replanning" demo language per the Phase 10 decision; update the architecture diagram to reflect the real pipeline (OSI SAF/ERA5/Copernicus Marine/BYU feeding real harmonisation, not "Synthetic Demo Generator" as a peer data source feeding the same pipeline as real sources, which is how the current diagram presents it); add a "What This System Does NOT Do" section checked against what was actually built; update the 5-minute demo procedure to reflect real behaviour (including what a refusal looks like, since that is now a real and demonstrable safety behaviour worth showing a jury, not something to hide).
> 4. Update `DATA_SOURCES.md` with the final, verified list of sources, their actual date ranges and grids (from Phase 2's verification), and account/credential setup instructions.
> 5. Retire or clearly archive `PROJECT_PLAN.md`'s original phase list (Phase 1 through whatever it originally specified) since this migration document has superseded it, and note that explicitly at the top of the file rather than leaving two conflicting plans in the repository.
> 6. Write the two model cards (`docs/models/sea_ice_model_card.md`, `docs/models/iceberg_model_card.md`) if not already finalised in Phases 5 and 6, and `docs/FALLBACK.md` describing exactly what happens when each dependency is missing.
> 7. Do a final search for leftover `TODO`, stub functions, `NotImplementedError`, and any remaining placeholder values (especially the risk table, if it is still a placeholder), and either resolve them or list them explicitly in the README's limitations section.
> 8. Run `verify.py` end to end and confirm it passes, then deliberately hand-edit one number in `README.md` to be wrong and confirm `verify.py` catches it, then revert.
> 9. Produce a final before/after comparison document, `docs/MIGRATION_SUMMARY.md`, contrasting the Phase 0 claims inventory and screenshots against the final real results and screenshots — this is useful both as an internal record and as material for explaining the project's development story to a jury.

> **Exit criteria.** `verify.py` passes and is proven to catch a deliberately wrong number. No document in the repository contradicts another. No unresolved stub or placeholder is left undocumented. `docs/MIGRATION_SUMMARY.md` exists. Merge `migration/real-data` to `main`. Commit as "Phase 12: documentation rewrite, verification script, migration complete."

---

# Appendix — Phase-to-File Quick Reference

| Phase | Primary files touched |
| ----- | ----- |
| 0 | git tags/branches, `docs/MIGRATION_LOG.md` |
| 1 | `app/core/provenance.py`, `*_service.py` fallback patterns, `app/schemas/*`, `DemoBanner.tsx`, `FreshnessTag.tsx` |
| 2 | `app/sources/*.py` (new: `osisaf_source.py`, `era5_source.py`, `currents_source.py`; extended: `iceberg_source.py`), `app/core/checks.py`, `scripts/verify_datasets.py` |
| 3 | `app/core/grid.py`, `app/harmonise/*`, `alembic/versions/003_provenance_and_grid.py` |
| 4 | `app/evaluation/*` (new module), `scripts/run_baselines.py` |
| 5 | `app/ml/seaice_pixel.py`, `seaice_unet.py`, `registry.py`; rewires `sea_ice_service.py`; retires old `sea_ice_model.py`/`train_sea_ice.py` |
| 6 | `app/ml/iceberg_physics.py`, `iceberg_residual.py`; rewires `iceberg_service.py`, removes `demo_service._iceberg_drift` from real-data paths |
| 7 | `config/risk_tables.yaml`, `app/risk/risk_index.py`, `app/fuel/fuel_model.py`; extends `risk_service.py`; uses existing `Vessel.ice_class` |
| 8 | `app/routing/cost_grid.py`, `astar.py`, `smooth.py`, `explain.py`; replaces internals of `route_service.py` |
| 9 | `app/routers/system.py`, `app/schemas/*`, demo_service reference audit |
| 10 | `frontend/src/pages/*.tsx`, `services/api.ts`, `types/index.ts`, new `UncertaintyPanel.tsx` |
| 11 | `app/agent/tools.py`, `polar_navigator.py` |
| 12 | `verify.py` (new, root), `README.md`, `MODEL_EVALUATION.md`, `DATA_SOURCES.md`, `PROJECT_PLAN.md`, `docs/MIGRATION_SUMMARY.md` |

*(End of migration document. This is a companion to `SIH26059_Documentation.md`, not a replacement for it — algorithms, interfaces, and non-negotiable principles referenced above are specified there in full.)*
