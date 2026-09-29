import numpy as np
from app.core.grid import AnalysisGrid
from app.harmonise.regrid import regrid_latlon
from app.harmonise.dataset_builder import build_dataset

def test_grid_round_trip_including_dateline():
    grid = AnalysisGrid.from_parameters("EPSG:3031", -2e6, -2e6, 100000, (40,40))
    lon = np.array([179.0, -179.0, 0.0]); lat = np.array([-60.0,-70.0,-75.0])
    x,y = grid.lonlat_to_xy(lon,lat); lon2,lat2 = grid.xy_to_lonlat(x,y)
    assert np.max(np.abs(((lon2-lon+180)%360)-180)) < 1e-8
    assert np.max(np.abs(lat2-lat)) < 1e-8
    assert np.all(grid.cell_area_km2() > 0)

def test_regrid_analytic_field():
    grid = AnalysisGrid.from_parameters("EPSG:3031", -2e6, -2e6, 100000, (40,40))
    lat=np.linspace(-80,-55,101); lon=np.linspace(-180,180,145)
    field=lat[:,None] + 2*lon[None,:]
    out=regrid_latlon(field,lat,lon,grid)
    tlon,tlat=grid.xy_to_lonlat(*np.meshgrid(grid.x,grid.y))
    valid=np.isfinite(out)
    np.testing.assert_allclose(out[valid], (tlat+2*tlon)[valid], atol=1e-8)

def test_dataset_builder_shapes():
    ds=build_dataset(np.zeros((20,4,5)), input_days=3, leads=2)
    assert ds.X.shape == (16,3,1,4,5); assert ds.Y.shape == (16,2,4,5); assert ds.mask.shape == (4,5)
