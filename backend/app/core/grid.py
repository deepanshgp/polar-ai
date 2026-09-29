"""Common projected analysis grid."""
from dataclasses import dataclass
import numpy as np
from pyproj import CRS, Transformer, Geod

@dataclass
class AnalysisGrid:
    projection: CRS
    x: np.ndarray
    y: np.ndarray
    land_mask: np.ndarray
    @classmethod
    def from_parameters(cls, projection, x_origin, y_origin, spacing_m, shape, land_mask=None):
        ny, nx = shape
        x = x_origin + np.arange(nx) * spacing_m
        y = y_origin + np.arange(ny) * spacing_m
        return cls(CRS.from_user_input(projection), x, y, np.zeros((ny,nx), dtype=bool) if land_mask is None else land_mask)
    def lonlat_to_xy(self, lon, lat):
        return Transformer.from_crs("EPSG:4326", self.projection, always_xy=True).transform(lon, lat)
    def xy_to_lonlat(self, x, y):
        return Transformer.from_crs(self.projection, "EPSG:4326", always_xy=True).transform(x, y)
    def contains(self, x, y):
        return (np.asarray(x) >= self.x.min()) & (np.asarray(x) <= self.x.max()) & (np.asarray(y) >= self.y.min()) & (np.asarray(y) <= self.y.max())
    def cell_area_km2(self):
        xx, yy = np.meshgrid(self.x, self.y)
        lon1, lat1 = self.xy_to_lonlat(xx, yy)
        lon2, lat2 = self.xy_to_lonlat(xx + np.median(np.diff(self.x)), yy + np.median(np.diff(self.y)))
        geod = Geod(ellps="WGS84")
        area, _ = geod.polygon_area_perimeter([lon1[0,0],lon2[0,0],lon2[0,-1],lon1[0,-1]], [lat1[0,0],lat2[0,0],lat2[0,-1],lat1[0,-1]])
        return np.full(self.land_mask.shape, abs(area) / 1e6)
