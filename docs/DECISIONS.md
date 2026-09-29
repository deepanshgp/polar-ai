# Decisions

## Phase 1

- `Provenance` is a separate immutable dataclass rather than a replacement for `FreshnessRegistry`. Provenance describes the identity, units, grid, valid time, and retrieval of a specific product; freshness is an operational registry of source status and age. The two concerns complement each other and can be attached to the same response.
- The legacy internal `live`/`offline` wording is retained only where it is part of configuration or freshness display compatibility. API `data_mode` values are normalized to exactly `real`, `demo`, or `unavailable`.
