"""
Ocean Service — Open-Meteo Marine real data (free, no key required).
LIVE mode: returns OFFLINE if fetch failed.
DEMO mode: returns synthetic current grid.
"""
import math
from datetime import datetime, timezone
from app.core.freshness import FreshnessRegistry, DataMode
from app.core.live_gate import check_or_offline, allow_demo_fallback


def _freshness_tag(is_real: bool) -> dict:
    f = FreshnessRegistry.get("ocean")
    return {
        "freshness": f.to_dict() if f else None,
        "is_real": is_real,
        "data_mode": DataMode.REAL.value if is_real else (DataMode.UNAVAILABLE.value if not allow_demo_fallback() else DataMode.DEMO.value),
    }


def _get_real_grid():
    try:
        from app.sources.ocean_source import get_ocean_source
        grid = get_ocean_source().get_grid()
        return (grid if grid else []), None
    except Exception as exc:
        return [], str(exc)


def get_current_ocean():
    grid, error = _get_real_grid()
    has_real = bool(grid)

    gate = check_or_offline("ocean", has_real,
        error or "Open-Meteo Marine data not yet fetched.")
    if gate is not None:
        return gate

    if has_real:
        avg_speed = sum(p["current_speed_ms"] for p in grid) / len(grid)
        sst_vals = [p["sea_surface_temp_celsius"] for p in grid
                    if p.get("sea_surface_temp_celsius") is not None]
        avg_sst = round(sum(sst_vals) / len(sst_vals), 1) if sst_vals else None
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "grid_points": grid,
            "avg_current_speed_ms": round(avg_speed, 3),
            "avg_sst_celsius": avg_sst,
            "source": "Open-Meteo Marine (wave model + ACC current estimate)",
            "note": "SST not available from Open-Meteo Marine. CMEMS credentials needed for SST.",
        }
        result.update(_freshness_tag(True))
        return result

    from app.services.demo_service import get_ocean as _demo_oc
    result = _demo_oc()
    result.update(_freshness_tag(False))
    return result


def get_nearest(lat: float, lon: float):
    grid, error = _get_real_grid()
    if grid:
        pt = min(grid, key=lambda p:
                 math.sqrt((p["latitude"] - lat)**2 + (p["longitude"] - lon)**2))
        return {**pt, **_freshness_tag(True)}

    gate = check_or_offline("ocean", False, error or "Open-Meteo Marine data unavailable.")
    if gate is not None:
        return gate

    from app.services.demo_service import get_ocean as _demo_oc
    demo_grid = _demo_oc()["grid_points"]
    nearest = min(demo_grid, key=lambda p:
                  math.sqrt((p["latitude"] - lat)**2 + (p["longitude"] - lon)**2))
    return {**nearest, **_freshness_tag(False)}
