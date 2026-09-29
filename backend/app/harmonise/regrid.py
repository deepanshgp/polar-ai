import numpy as np
from scipy.interpolate import RegularGridInterpolator
from app.core.grid import AnalysisGrid

def regrid_latlon(values, lat, lon, grid: AnalysisGrid, method="linear"):
    """Interpolate a regular lat/lon field onto projected grid coordinates."""
    xx, yy = np.meshgrid(grid.x, grid.y)
    target_lon, target_lat = grid.xy_to_lonlat(xx, yy)
    interp = RegularGridInterpolator((np.asarray(lat), np.asarray(lon)), np.asarray(values), method=method, bounds_error=False, fill_value=np.nan)
    return interp(np.stack([target_lat.ravel(), target_lon.ravel()], axis=-1)).reshape(xx.shape)
