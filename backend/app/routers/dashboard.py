"""
POLAR-AI Dashboard Router v2
Fully real-data driven. No demo_service calls in LIVE mode.
"""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.core.freshness import FreshnessRegistry
from app.core.live_gate import allow_demo_fallback

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db)):
    """
    Dashboard statistics driven entirely from real data sources.
    In LIVE mode: all values come from real external feeds.
    In DEMO mode: synthetic data clearly labelled.
    """
    now = datetime.now(timezone.utc)
    mode = settings.effective_data_mode

    # ── Active vessel ──────────────────────────────────────────────────────────
    vessel_info = _get_vessel_info()

    # ── Sea ice ────────────────────────────────────────────────────────────────
    sea_ice_info = _get_sea_ice_info()

    # ── Icebergs ───────────────────────────────────────────────────────────────
    iceberg_info = _get_iceberg_info()

    # ── Weather ────────────────────────────────────────────────────────────────
    weather_info = _get_weather_info(vessel_info.get("latitude"), vessel_info.get("longitude"))

    # ── Ocean ──────────────────────────────────────────────────────────────────
    ocean_info = _get_ocean_info(vessel_info.get("latitude"), vessel_info.get("longitude"))

    # ── Navigation risk ───────────────────────────────────────────────────────
    risk_info = _get_risk_info(vessel_info.get("latitude"), vessel_info.get("longitude"))

    # ── Forecast accuracy (from stored metrics) ───────────────────────────────
    forecast_accuracy = _get_forecast_accuracy()

    # ── System status ──────────────────────────────────────────────────────────
    system_status = FreshnessRegistry.summary()

    # ── Alerts ────────────────────────────────────────────────────────────────
    unread_alerts = 0
    try:
        from app.services.alert_service import AlertService
        unread_alerts = AlertService.get_unread_count()
    except Exception:
        pass

    return {
        # ── Vessel ────────────────────────────────────────────────────────────
        "vessel_name":         vessel_info.get("name"),
        "vessel_mmsi":         vessel_info.get("mmsi"),
        "vessel_lat":          vessel_info.get("latitude"),
        "vessel_lon":          vessel_info.get("longitude"),
        "vessel_speed_knots":  vessel_info.get("speed"),
        "vessel_heading_deg":  vessel_info.get("heading"),
        "vessel_course_deg":   vessel_info.get("course"),
        "vessel_status":       vessel_info.get("navigation_status", "unknown"),
        "vessel_destination":  vessel_info.get("destination"),
        "vessel_data_mode":    vessel_info.get("data_mode", "offline"),
        "vessel_age_seconds":  vessel_info.get("age_seconds"),
        "vessel_source":       vessel_info.get("source"),

        # ── Sea Ice ───────────────────────────────────────────────────────────
        "sea_ice_coverage_pct": (sea_ice_info.get("coverage_pct") if sea_ice_info.get("coverage_pct") is not None else 0.0),
        "sea_ice_extent_km2":   (sea_ice_info.get("extent_km2") if sea_ice_info.get("extent_km2") is not None else 0.0),
        "sea_ice_source":       sea_ice_info.get("source"),
        "sea_ice_updated":      sea_ice_info.get("last_updated"),
        "sea_ice_data_mode":    sea_ice_info.get("data_mode", "offline"),

        # ── Icebergs ──────────────────────────────────────────────────────────
        "active_icebergs":      iceberg_info.get("count", 0),
        "high_risk_icebergs":   iceberg_info.get("high_risk_count", 0),
        "iceberg_source":       iceberg_info.get("source"),
        "iceberg_data_mode":    iceberg_info.get("data_mode", "offline"),

        # ── Weather ───────────────────────────────────────────────────────────
        "avg_wind_speed_ms":    weather_info.get("wind_speed_ms"),
        "avg_sst_celsius":      ocean_info.get("sst_celsius"),
        "weather_source":       weather_info.get("source"),
        "weather_data_mode":    weather_info.get("data_mode", "offline"),

        # ── Ocean ─────────────────────────────────────────────────────────────
        "avg_current_speed_ms": ocean_info.get("current_speed_ms"),
        "ocean_source":         ocean_info.get("source"),
        "ocean_data_mode":      ocean_info.get("data_mode", "offline"),

        # ── Risk ──────────────────────────────────────────────────────────────
        "current_risk_score":    risk_info.get("total_risk_score", 0) * 100,
        "current_risk_category": risk_info.get("risk_category", "unknown"),
        "sea_ice_risk":          risk_info.get("sea_ice_risk", 0) * 100,
        "iceberg_risk":          risk_info.get("iceberg_risk", 0) * 100,
        "weather_risk":          risk_info.get("weather_risk", 0) * 100,
        "ocean_risk":            risk_info.get("ocean_risk", 0) * 100,
        "risk_data_mode":        risk_info.get("data_mode", "live"),

        # ── Meta ──────────────────────────────────────────────────────────────
        "effective_data_mode":  mode,
        "data_mode":            mode,
        "system_status":        system_status,
        "unread_alerts":        unread_alerts,
        "forecast_accuracy":    forecast_accuracy,
        "last_updated":         now.isoformat(),
        "disclaimer":           (
            "LIVE DATA MODE — Decision support only. "
            "Not a certified navigation system."
            if mode == "live"
            else "DEMO / SIMULATION DATA — Not for real navigation."
        ),
    }


# ── Helper functions ───────────────────────────────────────────────────────────

def _get_vessel_info() -> dict:
    """Get active vessel info from AIS manager."""
    try:
        from app.services.ais.ais_manager import get_registry
        reg = get_registry()
        v = reg.get_active_vessel()
        if v and v.get("is_real"):
            return v
    except Exception:
        pass

    # Fallback: legacy single-vessel service
    try:
        from app.sources.vessel_source import get_vessel_service
        pos = get_vessel_service().get_position()
        if pos.get("is_real"):
            return pos
    except Exception:
        pass

    if allow_demo_fallback():
        return {
            "mmsi": "DEMO", "name": "RV Polar Explorer [DEMO]",
            "latitude": -66.0, "longitude": -60.0,
            "speed": 11.5, "heading": 145.0, "course": 145.0,
            "navigation_status": "underway", "source": "demo",
            "data_mode": "demo", "is_real": False,
        }

    return {
        "mmsi": None, "name": None, "latitude": None, "longitude": None,
        "data_mode": "offline", "is_real": False,
    }


def _get_sea_ice_info() -> dict:
    """Get latest sea-ice extent from NSIDC source."""
    try:
        from app.sources.sea_ice_source import get_sea_ice_source
        from app.core.freshness import FreshnessRegistry
        src = get_sea_ice_source()
        latest = src.get_latest_extent()
        if latest:
            f = FreshnessRegistry.get("sea_ice")
            return {
                "coverage_pct": round(latest.get("coverage_pct", 0), 1),
                "extent_km2": round(latest.get("extent_km2", 0), 0),
                "source": latest.get("source", "NSIDC"),
                "last_updated": latest.get("date"),
                "data_mode": "live",
            }
    except Exception:
        pass

    if allow_demo_fallback():
        from app.services.demo_service import get_sea_ice_grid
        grid = get_sea_ice_grid("low")
        return {"coverage_pct": grid["coverage_pct"],
                "extent_km2": grid["extent_km2"],
                "source": "demo", "data_mode": "demo"}

    return {"coverage_pct": 0.0, "extent_km2": 0.0,
            "source": "unavailable", "data_mode": "offline"}


def _get_iceberg_info() -> dict:
    try:
        from app.sources.iceberg_source import get_iceberg_source
        icebergs = get_iceberg_source().get_icebergs()
        if icebergs:
            return {
                "count": len(icebergs),
                "high_risk_count": sum(
                    1 for ib in icebergs
                    if (ib.get("area_km2") or 0) > 1000
                ),
                "source": "US National Ice Center",
                "data_mode": "live",
            }
    except Exception:
        pass

    if allow_demo_fallback():
        from app.services.demo_service import get_icebergs
        ibs = get_icebergs()
        return {"count": ibs["total_count"],
                "high_risk_count": ibs["high_risk_count"],
                "source": "demo", "data_mode": "demo"}

    return {"count": 0, "high_risk_count": 0,
            "source": "unavailable", "data_mode": "offline"}


def _get_weather_info(lat, lon) -> dict:
    try:
        from app.sources.weather_source import get_weather_source
        grid = get_weather_source().get_grid()
        if grid:
            import math
            if lat is not None and lon is not None:
                pt = min(grid, key=lambda p:
                         math.sqrt((p["latitude"]-lat)**2 + (p["longitude"]-lon)**2))
            else:
                pt = grid[0]
            return {
                "wind_speed_ms": pt.get("wind_speed_ms"),
                "wind_direction_deg": pt.get("wind_direction_deg"),
                "air_temp_celsius": pt.get("air_temp_celsius"),
                "source": pt.get("source", "Open-Meteo"),
                "data_mode": "live",
            }
    except Exception:
        pass

    if allow_demo_fallback():
        from app.services.demo_service import get_weather
        wx = get_weather()
        return {"wind_speed_ms": wx["avg_wind_speed_ms"],
                "source": "demo", "data_mode": "demo"}

    return {"wind_speed_ms": None, "source": "unavailable", "data_mode": "offline"}


def _get_ocean_info(lat, lon) -> dict:
    try:
        from app.sources.ocean_source import get_ocean_source
        grid = get_ocean_source().get_grid()
        if grid:
            import math
            if lat is not None and lon is not None:
                pt = min(grid, key=lambda p:
                         math.sqrt((p["latitude"]-lat)**2 + (p["longitude"]-lon)**2))
            else:
                pt = grid[0]
            return {
                "current_speed_ms": pt.get("current_speed_ms"),
                "current_direction_deg": pt.get("current_direction_deg"),
                "sst_celsius": pt.get("sea_surface_temp_celsius"),
                "source": pt.get("source", "Open-Meteo Marine"),
                "data_mode": "live",
            }
    except Exception:
        pass

    if allow_demo_fallback():
        from app.services.demo_service import get_ocean
        oc = get_ocean()
        return {"current_speed_ms": oc["avg_current_speed_ms"],
                "sst_celsius": oc["avg_sst_celsius"],
                "source": "demo", "data_mode": "demo"}

    return {"current_speed_ms": None, "sst_celsius": None,
            "source": "unavailable", "data_mode": "offline"}


def _get_risk_info(lat, lon) -> dict:
    if lat is None or lon is None:
        return {"total_risk_score": 0, "risk_category": "unknown",
                "sea_ice_risk": 0, "iceberg_risk": 0,
                "weather_risk": 0, "ocean_risk": 0, "data_mode": "offline"}
    try:
        from app.services.risk_service import calculate_risk
        from app.schemas.routes import RiskCalculateRequest
        return calculate_risk(RiskCalculateRequest(
            latitude=lat, longitude=lon, radius_km=100.0))
    except Exception:
        return {"total_risk_score": 0, "risk_category": "unknown",
                "sea_ice_risk": 0, "iceberg_risk": 0,
                "weather_risk": 0, "ocean_risk": 0, "data_mode": "offline"}


def _get_forecast_accuracy() -> list:
    """Return model performance from stored metrics (not fabricated)."""
    import os, json
    metrics_path = os.path.join(settings.MODELS_DIR, "sea_ice_metrics.json")
    try:
        if os.path.exists(metrics_path):
            with open(metrics_path) as f:
                m = json.load(f)
            return [
                {"horizon": k, "mae": v.get("mae"), "rmse": v.get("rmse"),
                 "skill_score": v.get("skill_score")}
                for k, v in m.items()
            ]
    except Exception:
        pass
    return []  # No fabricated accuracy metrics
