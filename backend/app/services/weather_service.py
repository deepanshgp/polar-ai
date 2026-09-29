"""
Weather Service — Open-Meteo real NWP data (free, no key required).
LIVE mode: returns OFFLINE if fetch failed.
DEMO mode: returns synthetic wind/temp grid.
"""
import math
from datetime import datetime, timezone
from app.core.freshness import FreshnessRegistry, DataMode
from app.core.live_gate import check_or_offline, allow_demo_fallback, offline_response


def _freshness_tag(is_real: bool) -> dict:
    f = FreshnessRegistry.get("weather")
    return {
        "freshness": f.to_dict() if f else None,
        "is_real": is_real,
        "data_mode": DataMode.REAL.value if is_real else (DataMode.UNAVAILABLE.value if not allow_demo_fallback() else DataMode.DEMO.value),
    }


def _get_real_grid():
    try:
        from app.sources.weather_source import get_weather_source
        grid = get_weather_source().get_grid()
        return (grid if grid else []), None
    except Exception as exc:
        return [], str(exc)


def get_current_weather():
    grid, error = _get_real_grid()
    has_real = bool(grid)

    gate = check_or_offline("weather", has_real,
        error or "Open-Meteo weather data not yet fetched.")
    if gate is not None:
        return gate

    if has_real:
        avg_wind = sum(p["wind_speed_ms"] for p in grid) / len(grid)
        min_temp = min(p["air_temp_celsius"] for p in grid)
        result = {
            "timestamp": grid[0].get("observation_time", datetime.now(timezone.utc).isoformat()),
            "grid_points": grid,
            "avg_wind_speed_ms": round(avg_wind, 2),
            "min_temp_celsius": round(min_temp, 1),
        }
        result.update(_freshness_tag(True))
        return result

    # Demo fallback (auto/demo mode only)
    from app.services.demo_service import get_weather as _demo_wx
    result = _demo_wx()
    result.update(_freshness_tag(False))
    return result


def get_forecast(horizon_hours: int = 72):
    """Forecast — demo model only (clearly labelled). Open-Meteo hourly forecast coming soon."""
    grid, error = _get_real_grid()
    has_real = bool(grid)

    if has_real:
        # Use current real conditions as T+0, physics extrapolation for horizons
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "forecasts": [{"horizon_hours": 0, **_build_real_forecast_point(grid)}],
            "source": "Open-Meteo NWP (current observation)",
            "note": "Forecast horizon not yet implemented for real weather. Showing latest observation.",
        }
        result.update(_freshness_tag(True))
        return result

    gate = check_or_offline("weather", False, error or "No weather data available.")
    if gate is not None:
        return gate

    from app.services.demo_service import get_weather_forecast as _demo_fcst
    result = _demo_fcst(horizon_hours)
    result.update(_freshness_tag(False))
    return result


def _build_real_forecast_point(grid):
    avg_wind = sum(p["wind_speed_ms"] for p in grid) / len(grid)
    avg_temp = sum(p["air_temp_celsius"] for p in grid) / len(grid)
    avg_press = sum(p["sea_level_pressure_hpa"] for p in grid) / len(grid)
    return {
        "avg_wind_speed_ms": round(avg_wind, 2),
        "avg_temp_celsius": round(avg_temp, 1),
        "avg_pressure_hpa": round(avg_press, 1),
        "grid_point_count": len(grid),
    }


def get_nearest(lat: float, lon: float):
    """Get weather at nearest grid point to given coordinates."""
    grid, error = _get_real_grid()
    if grid:
        pt = min(grid, key=lambda p:
                 math.sqrt((p["latitude"] - lat)**2 + (p["longitude"] - lon)**2))
        return {**pt, **_freshness_tag(True)}

    gate = check_or_offline("weather", False, error or "Weather data unavailable.")
    if gate is not None:
        return gate

    import math as _math
    demo_grid = _get_demo_grid()
    nearest = min(demo_grid, key=lambda p:
                  _math.sqrt((p["latitude"] - lat)**2 + (p["longitude"] - lon)**2))
    return {**nearest, **_freshness_tag(False)}


def _get_demo_grid():
    from app.services.demo_service import get_weather as _demo_wx
    return _demo_wx()["grid_points"]
