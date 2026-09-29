import numpy as np
REGIMES={"open":(0,.15),"mizt":(.15,.50),"pack":(.50,.85),"consolidated":(.85,1.0001)}
def regime_masks(reference_field):
    a=np.asarray(reference_field); return {name:(a>=lo)&(a<hi) for name,(lo,hi) in REGIMES.items()}
def edge_band_mask(reference_field,width_cells):
    a=np.asarray(reference_field); return (a>0.15-width_cells*.01)&(a<0.15+width_cells*.01)
