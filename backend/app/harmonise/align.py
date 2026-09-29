import pandas as pd

def align_daily(ds, time_name="time", aggregation="mean"):
    """Align a time-indexed xarray Dataset to daily UTC bins without gap filling."""
    if time_name not in ds.coords and time_name not in ds.dims: raise ValueError(f"missing {time_name} coordinate")
    ds = ds.assign_coords({time_name: pd.to_datetime(ds[time_name].values, utc=True)})
    return getattr(ds.resample({time_name: "1D"}), aggregation)()
