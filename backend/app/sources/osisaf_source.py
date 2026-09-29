"""OSI SAF/Copernicus gridded sea-ice concentration adapter."""
from datetime import date, datetime, timezone
from pathlib import Path
import os
import xarray as xr
from app.core.provenance import Provenance
from app.core.checks import ValidationReport, validate_dataset

class OsiSafSource:
    source_id = "osisaf_sic"
    def is_configured(self): return bool(os.getenv("COPERNICUS_MARINE_USERNAME") and os.getenv("COPERNICUS_MARINE_PASSWORD"))
    def fetch(self, start: date, end: date, cfg=None) -> list[Path]:
        raise RuntimeError("OSI SAF download endpoint must be configured from the provider product catalogue")
    def load(self, paths: list[Path]) -> xr.Dataset:
        if not paths: raise ValueError("No OSI SAF files supplied")
        ds = xr.open_mfdataset(paths, combine="by_coords")
        variable = next((n for n in ("ice_concentration", "sic", "ice_conc") if n in ds), None)
        if variable is None: raise ValueError("OSI SAF concentration variable not found")
        da = ds[variable]
        if da.attrs.get("units", "").lower() in ("%", "percent", "percentage") or float(da.max()) > 1.0: da = da / 100.0
        flag = next((n for n in ("status_flag", "quality_flag", "land_flag") if n in ds), None)
        if flag: da = da.where(ds[flag] == 0)
        out = da.to_dataset(name="sic")
        out["sic"].attrs["units"] = "1"
        out.attrs["provenance"] = Provenance("Copernicus Marine / OSI SAF", "OSI SAF SIC", "sic", "1", None, datetime.now(timezone.utc), None, "provider-native", "Flags and land cells masked").__dict__
        return out
    def validate(self, ds: xr.Dataset, cfg=None) -> ValidationReport: return validate_dataset(ds, ["sic"], {"sic": (0.0, 1.0)})
