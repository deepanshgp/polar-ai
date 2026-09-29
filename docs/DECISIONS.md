# Decisions

## Phase 1

- `Provenance` is a separate immutable dataclass rather than a replacement for `FreshnessRegistry`. Provenance describes the identity, units, grid, valid time, and retrieval of a specific product; freshness is an operational registry of source status and age. The two concerns complement each other and can be attached to the same response.
- The legacy internal `live`/`offline` wording is retained only where it is part of configuration or freshness display compatibility. API `data_mode` values are normalized to exactly `real`, `demo`, or `unavailable`.

## Phase 2

- OSI SAF, ERA5, and Copernicus Marine adapters expose the documented fetch/load/validate contract but intentionally do not invent provider download URLs or variable names. They require product configuration or downloaded paths; unresolved provider access is reported as unavailable.
- No synthetic files were added under `backend/tests/fixtures/`: the workspace contains only demo data, and the project rules prohibit relabelling those files as real downloads. Fixtures will be added from verified provider downloads when credentials/product paths are available.
