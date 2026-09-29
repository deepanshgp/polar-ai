"""Copernicus Marine surface-current adapter."""
from datetime import date, datetime, timezone
from pathlib import Path
import os, numpy as np, xarray as xr
from app.core.provenance import Provenance
from app.core.checks import ValidationReport, validate_dataset
from app.sources.era5_source import rotate_to_grid

class CurrentsSource:
    source_id = "copernicus_currents"
    def is_configured(self): return bool(os.getenv("COPERNICUS_MARINE_USERNAME") and os.getenv("COPERNICUS_MARINE_PASSWORD"))
    def fetch(self, start: date, end: date, cfg=None) -> list[Path]: raise RuntimeError("Copernicus Marine fetch requires product configuration")
    def load(self, paths):
        ds = xr.open_mfdataset(paths, combine="by_coords")
        ds = ds.rename({k:v for k,v in {"uo":"current_u","vo":"current_v"}.items() if k in ds})
        ds.attrs["provenance"] = Provenance("Copernicus Marine", "GLOBAL_ANALYSISFORECAST_PHY_001_024", "current_u,current_v", "m/s", None, datetime.now(timezone.utc), None, "provider-native", "Shallowest available level").__dict__
        return ds
    def validate(self, ds, cfg=None): return validate_dataset(ds, ["current_u","current_v"])
