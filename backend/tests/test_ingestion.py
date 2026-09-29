import numpy as np
from app.sources.era5_source import rotate_to_grid

def test_rotate_to_grid_hand_computed_longitudes():
    u, v = rotate_to_grid(1.0, 0.0, np.array([0.0, 90.0, 180.0, 270.0]))
    np.testing.assert_allclose(u, [1.0, 0.0, -1.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(v, [0.0, -1.0, 0.0, 1.0], atol=1e-12)
