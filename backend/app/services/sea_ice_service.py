"""
Sea Ice Service — LIVE mode uses NSIDC real data only.
DEMO mode uses synthetic data.
"""
from datetime import datetime, timezone
from app.config import settings
from app.core.freshness import FreshnessRegistry, DataStatus, DataMode
from app.core.live_gate import check_or_offline, allow_demo_fallback, annotate_response
from app.schemas.sea_ice import SeaIcePredictRequest


def _freshness_tag(is_real: bool) -> dict:
    f = FreshnessRegistry.get("sea_ice")
    return {
        "freshness": f.to_dict() if f else None,
        "is_real": is_real,
        "data_mode": DataMode.REAL.value if is_real else (DataMode.UNAVAILABLE.value if not allow_demo_fallback() else DataMode.DEMO.value),
    }


def _get_real_source():
    try:
        from app.sources.sea_ice_source import get_sea_ice_source
        return get_sea_ice_source(), None
    except Exception as exc:
        return None, str(exc)


def _get_real_latest():
    src, error = _get_real_source()
    if src:
        return src.get_latest_extent(), None
    return None, error


def get_current_sea_ice(resolution: str = "low"):
    """
    Returns current sea-ice grid.
    LIVE mode: real NSIDC extent overlaid on spatial physics model.
    DEMO mode: fully synthetic grid.
    """
    real_extent, error = _get_real_latest()
    has_real = real_extent is not None

    # Gate: LIVE mode with no real data → OFFLINE
    gate = check_or_offline("sea_ice", has_real,
        error or "NSIDC sea-ice data not yet fetched. Check /api/live/status.")
    if gate is not None:
        return gate

    # If real data exists, overlay real scalars on spatial grid
    from app.services.demo_service import get_sea_ice_grid as _demo_grid
    result = _demo_grid(resolution)

    if has_real:
        result["coverage_pct"] = round(real_extent["coverage_pct"], 1)
        result["extent_km2"]   = round(real_extent["extent_km2"], 0)
        result["source"]       = real_extent.get("source", "NSIDC G02135 v3")
        result["observation_date"] = real_extent.get("date")
        # The spatial grid is still model-based (NSIDC doesn't provide free gridded NetCDF)
        result["spatial_note"] = (
            "Spatial distribution is a physics model. "
            "Scalar extent/area values are from NSIDC Sea Ice Index."
        )
    else:
        result["source"] = "demo_physics_model"

    result.update(_freshness_tag(has_real))
    return result


def get_history(days: int = 90):
    """Historical time series — real NSIDC daily CSV in LIVE mode."""
    src, error = _get_real_source()
    has_real = bool(src and src.get_history(days=1))

    gate = check_or_offline("sea_ice", has_real,
        error or "No historical sea-ice data available yet.")
    if gate is not None:
        return gate

    if has_real:
        records = src.get_history(days=days)
        if records:
            result = {
                "start_date": records[0]["date"],
                "end_date": records[-1]["date"],
                "data_points": records,
                "source": "NSIDC Sea Ice Index G02135 v3",
                "note": "Daily sea-ice extent from satellite passive microwave data.",
            }
            result.update(_freshness_tag(True))
            return result

    if not allow_demo_fallback():
        return offline_response("sea_ice", "No historical data available.")

    from app.services.demo_service import get_sea_ice_history as _demo_hist
    result = _demo_hist(days)
    result.update(_freshness_tag(False))
    return result


def get_forecast(horizon_hours: int = 72):
    """
    Sea-ice forecast. Currently always uses the physics baseline model.
    Labels clearly as MODEL FORECAST, not live data.
    """
    from app.services.demo_service import get_sea_ice_forecast as _demo_fcst
    forecasts = _demo_fcst(horizon_hours)
    target = next((f for f in forecasts if f["horizon_hours"] == horizon_hours), forecasts[-1])
    target["model_note"] = (
        "Physics-based forecast. Not a certified operational forecast."
    )
    target["source"] = "POLAR-AI physics baseline model"
    latest, _ = _get_real_latest()
    f_tag = _freshness_tag(latest is not None)
    target.update(f_tag)
    return target


def predict(request: SeaIcePredictRequest):
    return get_forecast(request.horizon_hours)


def offline_response(source_id: str, message: str) -> dict:
    from app.core.live_gate import offline_response as _or
    return _or(source_id, message)
