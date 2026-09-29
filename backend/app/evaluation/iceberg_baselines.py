import numpy as np
def stationary(p0): return np.asarray(p0,dtype=float).copy()
def constant_velocity(p0,v_prev,dt): return np.asarray(p0,dtype=float)+np.asarray(v_prev,dtype=float)*dt
def physics_only(p0,current,wind,dt,wind_coeff): return np.asarray(p0,dtype=float)+(np.asarray(current)+wind_coeff*np.asarray(wind))*dt
