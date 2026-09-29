import numpy as np

def persistence(x_last, lead): return np.asarray(x_last).copy()
def climatology(train_dates, train_fields, target_dates):
    fields=np.asarray(train_fields); dates=list(train_dates)
    by_doy={}
    for d,f in zip(dates,fields): by_doy.setdefault(getattr(d,"timetuple",lambda:None)().tm_yday if hasattr(d,"timetuple") else int(d)%365,[]).append(f)
    return np.stack([np.mean(by_doy.get((getattr(d,"timetuple",lambda:None)().tm_yday if hasattr(d,"timetuple") else int(d)%365),fields),axis=0) for d in target_dates])
def damped_persistence(x_last, clim, lead, tau): return np.asarray(clim)+(np.asarray(x_last)-np.asarray(clim))*np.exp(-lead/float(tau))
