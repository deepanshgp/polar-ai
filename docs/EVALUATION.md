# Evaluation

## Phase 4 status

The leakage-safe split, baseline, metric, regime, and bootstrap utilities are implemented and tested. No `results/baselines.json` is generated because the repository does not yet contain a verified real harmonised dataset from Phase 3. `scripts/run_baselines.py` fails closed when that dataset is absent.

The previous synthetic claims (sea-ice skill scores 0.81/0.83/0.81 and iceberg errors 1.8–52.8 km) are superseded and must not be presented as real performance. They were produced from synthetic, spatially/temporally correlated data and a random split, so they do not measure generalisation under the required time- and identity-separated evaluation. They will be replaced only by script-generated results with sample counts, regimes, seasons, and uncertainty intervals.
