# Decisions

## Phase 1

- `Provenance` is a separate immutable dataclass rather than a replacement for `FreshnessRegistry`. Provenance describes the identity, units, grid, valid time, and retrieval of a specific product; freshness is an operational registry of source status and age. The two concerns complement each other and can be attached to the same response.
- The legacy internal `live`/`offline` wording is retained only where it is part of configuration or freshness display compatibility. API `data_mode` values are normalized to exactly `real`, `demo`, or `unavailable`.

## Phase 2

- OSI SAF, ERA5, and Copernicus Marine adapters expose the documented fetch/load/validate contract but intentionally do not invent provider download URLs or variable names. They require product configuration or downloaded paths; unresolved provider access is reported as unavailable.
- No synthetic files were added under `backend/tests/fixtures/`: the workspace contains only demo data, and the project rules prohibit relabelling those files as real downloads. Fixtures will be added from verified provider downloads when credentials/product paths are available.

## Phase 2.5

- The running stack was verified on 2026-09-29: PostgreSQL/PostGIS and the backend health check are healthy; frontend, API docs, and health endpoints returned HTTP 200.
- Docker logs still show background-update foreign-key failures for weather/ocean observation writes because generated `run_id` values are absent from `data_update_runs`. This is recorded for the next fix rather than hidden by the healthy container status.
- Browser logs showed 403 responses for legacy `/ws/vessels` and `/ws/live` attempts, while `/api/ws/live` was accepted. The supported websocket path is therefore `/api/ws/live` until the legacy client paths are removed or aliased.

## Phase 3

- Harmonised gridded arrays will live in NetCDF/Zarr files referenced by database metadata; the existing point-sample PostGIS tables remain for summaries, forecasts, and provenance. Storing every daily grid cell as an ORM row would create unnecessary volume and does not match the array-native source formats.
- The native OSI SAF projection, origin, spacing, and shape remain unresolved because no verified OSI SAF file was available from Phase 2. `config/domain.yaml` therefore uses explicit nulls and the grid API requires these values to be supplied before production harmonisation. EPSG:3031 is used only in synthetic analytic unit tests, never as a claimed source-grid value.

## Phase 4

- **Fixture dataset strategy.** Real OSI SAF downloads were blocked (404 from public endpoints; `copernicusmarine` not installed in the container image). Rather than block the entire evaluation harness, `scripts/build_fixture_dataset.py` generates a deterministic FIXTURE_SYNTHETIC harmonised dataset from a parameterised seasonal SIC cosine model on a regular 30×36 lat/lon grid (−80° to −55°, 2024–2025). This is clearly labelled throughout; no numbers from this run are presented as real-world skill. The harness is structurally ready to accept real data.
- **Domain projection for fixture.** `config/domain.yaml` is resolved to EPSG:4326 (geographic lat/lon) for the fixture grid, with explicit comment that EPSG:3031 (Antarctic Polar Stereographic) is the intended production projection once verified OSI SAF files arrive. `x_origin_m`, `y_origin_m`, `spacing_m`, and `shape` remain null pending Phase 2 real data.
- **Leakage gap size.** The time-split gap was set to `max_lead = 7` days so that no target cell within the validation or test block is ever predicted by a training-block input. `assert_no_leakage(split, max_lead=7)` is called in `run_baselines.py` and in the test suite.
- **Iceberg split dimension.** Icebergs are split by berg identity (name) first, then time, matching the §6.1 spec. This prevents the model from seeing the same physical iceberg in both train and test sets.
- **Bootstrap CI parameters.** n = 1 000, seed = 0 (fixed for reproducibility). CIs are on the per-cell absolute-error distribution across all test samples.
- **IIEE area approximation.** Cell areas are computed as flat-Earth (latitude-scaled rectangle) on the fixture's lat/lon grid. When real EASE2 or Polar Stereographic data arrive, `AnalysisGrid.cell_area_km2()` should be used instead.

