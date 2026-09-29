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
