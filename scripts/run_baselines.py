"""Run baselines only when verified real harmonised data is present."""
import json,sys
from pathlib import Path
root=Path(__file__).parents[1]; data=root/'data'/'processed'/'harmonised.npz'; results=root/'results'; results.mkdir(exist_ok=True)
if not data.exists():
    raise SystemExit("No verified real harmonised dataset at data/processed/harmonised.npz; refusing to fabricate results/baselines.json")
raise SystemExit("Dataset runner wiring is ready; implement source-specific NPZ loading before evaluation.")
