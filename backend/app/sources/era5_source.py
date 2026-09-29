"""ERA5 wind/temperature adapter and geographic-to-grid vector rotation."""
from datetime import date, datetime, timezone
from pathlib import Path
import os, numpy as np, xarray as xr
from app.core.provenance import Provenance
from app.core.checks import ValidationReport, validate_dataset

def rotate_to_grid(u, v, lon):
    """Rotate east/north components into a longitude-aligned polar grid."""
    a = np.deg2rad(lon)
    return np.asarray(u) * np.cos(a) + np.asarray(v) * np.sin(a), -np.asarray(u) * np.sin(a) + np.asarray(v) * np.cos(a)

class Era5Source:
    source_id = "era5"
    def is_configured(self): return bool(os.getenv("CDS_API_KEY"))
    def fetch(self, start: date, end: date, cfg=None) -> list[Path]: raise RuntimeError("ERA5 fetch requires CDS API configuration")
    def load(self, paths: list[Path]) -> xr.Dataset:
        ds = xr.open_mfdataset(paths, combine="by_coords")
        rename = {"u10":"wind_u", "v10":"wind_v", "t2m":"temperature_2m"}
        ds = ds.rename({k:v for k,v in rename.items() if k in ds})
        ds["temperature_2m"] = ds["temperature_2m"] - 273.15 if ds["temperature_2m"].attrs.get("units") == "K" else ds["temperature_2m"]
        ds["temperature_2m"].attrs["units"] = "degC"
        ds.attrs["provenance"] = Provenance("ECMWF/Copernicus", "ERA5", "wind_u,wind_v,temperature_2m", "m/s, m/s, degC", None, datetime.now(timezone.utc), None, "regular lat/lon", "Rotation deferred to analysis-grid longitude").__dict__
        return ds
    def validate(self, ds, cfg=None) -> ValidationReport: return validate_dataset(ds, ["wind_u","wind_v","temperature_2m"])
