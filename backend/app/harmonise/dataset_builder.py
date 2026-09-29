from dataclasses import dataclass
import numpy as np

@dataclass
class ModelDataset:
    X: np.ndarray
    static: np.ndarray
    doy: np.ndarray
    Y: np.ndarray
    mask: np.ndarray

def build_dataset(concentration, forcings=None, land_mask=None, input_days=7, leads=7):
    """Build [samples,T,C,H,W], static [S,H,W], doy [samples,2], Y [samples,L,H,W]."""
    c = np.asarray(concentration, dtype=float)
    if c.ndim != 3: raise ValueError("concentration must be [time,y,x]")
    t, h, w = c.shape
    forcings = [] if forcings is None else [np.asarray(f) for f in forcings]
    channels = [c] + forcings
    n = t - input_days - leads + 1
    if n <= 0: raise ValueError("not enough time steps")
    X = np.stack([np.stack([a[i:i+input_days] for a in channels], axis=1) for i in range(n)])
    Y = np.stack([c[i+input_days:i+input_days+leads] for i in range(n)])
    mask = np.ones((h,w), bool) if land_mask is None else ~np.asarray(land_mask, bool)
    static = np.stack([~mask], axis=0)
    doy = np.zeros((n,2), float)
    return ModelDataset(X, static, doy, Y, mask)
