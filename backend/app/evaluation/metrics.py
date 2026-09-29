import numpy as np
def _v(y,mask=None):
    a=np.asarray(y); return a[np.asarray(mask,dtype=bool)] if mask is not None else a.ravel()
def mae(y,yhat,mask=None): return float(np.mean(np.abs(_v(y,mask)-_v(yhat,mask))))
def rmse(y,yhat,mask=None): return float(np.sqrt(np.mean((_v(y,mask)-_v(yhat,mask))**2)))
def skill_vs(baseline_err,model_err): return float("nan") if baseline_err==0 else 1-model_err/baseline_err
def iiee(y,yhat,mask,area_km2,thresh=.15):
    wrong=(np.abs(np.asarray(y)-np.asarray(yhat))>thresh)&np.asarray(mask,bool)
    return float(np.sum(np.asarray(area_km2)[wrong]))
def position_error_km(true_xy,pred_xy): return np.linalg.norm(np.asarray(true_xy)-np.asarray(pred_xy),axis=-1)/1000
def bootstrap_ci(values,n=1000,seed=0):
    v=np.asarray(values,float); rng=np.random.default_rng(seed)
    if not len(v): return (float("nan"),float("nan"))
    samples=np.array([rng.choice(v,len(v),replace=True).mean() for _ in range(n)])
    return tuple(np.quantile(samples,[.025,.975]))
