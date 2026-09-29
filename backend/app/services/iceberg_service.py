"""
Iceberg Service — LIVE mode uses NIC real data only.
DEMO mode uses synthetic icebergs.

LIVE mode rule: If NIC data is unavailable, return OFFLINE — never show
fake A-76A / B-22A / demo coordinates.
"""
from datetime import datetime, timezone
from typing import Optional
from app.config import settings
from app.core.freshness import FreshnessRegistry, DataStatus, DataMode
from app.core.live_gate import check_or_offline, allow_demo_fallback, offline_response


def _freshness_tag(is_real: bool) -> dict:
    f = FreshnessRegistry.get("icebergs")
    return {
        "freshness": f.to_dict() if f else None,
        "is_real": is_real,
        "data_mode": DataMode.REAL.value if is_real else (DataMode.UNAVAILABLE.value if not allow_demo_fallback() else DataMode.DEMO.value),
    }


def _get_real_icebergs():
    try:
        from app.sources.iceberg_source import get_iceberg_source
        real = get_iceberg_source().get_icebergs()
        return (real if real else []), None
    except Exception as exc:
        return [], str(exc)


def _enrich_iceberg(ib: dict, idx: int) -> dict:
    """Add computed drift / risk to a real NIC iceberg record."""
    from app.services.demo_service import _iceberg_drift
    lat = ib.get("latitude", -65)
    lon = ib.get("longitude", -60)
    _, _, speed, direction = _iceberg_drift(lat, lon, 0, idx * 100)
    area = (ib.get("area_km2") or
            (ib.get("length_km", 20) or 20) * (ib.get("width_km", 8) or 8) * 0.85)
    risk = ("high" if area > 1000 else ("medium" if area > 200 else "low"))
    return {
        "id": f"nic-{ib['iceberg_name'].lower().replace(' ', '-')}",
        "iceberg_name": ib["iceberg_name"],
        "latitude": ib["latitude"],
        "longitude": ib["longitude"],
        "length_km": ib.get("length_km"),
        "width_km": ib.get("width_km"),
        "area_km2": round(float(area), 1),
        "drift_speed_kmh": round(float(speed), 3),
        "drift_direction_deg": round(float(direction), 1),
        "risk_level": risk,
        "status": "active",
        "last_observed_at": ib.get("last_observed_at"),
        "source": ib.get("source", "US National Ice Center"),
        "source_url": ib.get("source_url", "https://usicecenter.gov/Products/AntarcIcebergs"),
        "is_real": True,
        "data_mode": "live",
    }


def list_icebergs():
    real, error = _get_real_icebergs()
    has_real = bool(real)

    gate = check_or_offline("icebergs", has_real,
        error or "NIC iceberg data not yet available. Retrying hourly.")
    if gate is not None:
        return gate

    if has_real:
        enriched = [_enrich_iceberg(ib, i) for i, ib in enumerate(real)]
        result = {
            "icebergs": enriched,
            "total_count": len(enriched),
            "active_count": len(enriched),
            "high_risk_count": sum(1 for ib in enriched if ib["risk_level"] == "high"),
            "source": "US National Ice Center",
            "source_note": "Named Antarctic icebergs >18.5 km². Updated weekly by NIC.",
        }
        result.update(_freshness_tag(True))
        return result

    # Demo fallback (only in auto/demo mode)
    from app.services.demo_service import get_icebergs as _demo_ibs
    result = _demo_ibs()
    result.update(_freshness_tag(False))
    return result


def get_iceberg_detail(iceberg_name: str):
    real, error = _get_real_icebergs()
    has_real = bool(real)

    if has_real:
        ib_raw = next((r for r in real if r.get("iceberg_name") == iceberg_name), None)
        if ib_raw:
            idx = real.index(ib_raw)
            lat, lon = ib_raw["latitude"], ib_raw["longitude"]
            from datetime import timedelta
            from app.services.demo_service import _iceberg_drift
            positions = []
            for h_back in range(0, 30 * 24, 12):
                t = datetime.now(timezone.utc) - timedelta(hours=h_back)
                pl, po, spd, dirn = _iceberg_drift(lat, lon, -h_back, idx * 100 + h_back)
                positions.append({
                    "observed_at": t.isoformat(),
                    "latitude": round(pl, 4), "longitude": round(po, 4),
                    "speed_kmh": round(spd, 3), "direction_deg": round(dirn, 1),
                    "confidence": 0.95 if h_back < 48 else 0.8,
                    "source": "physics_drift_model",
                })
            enriched = _enrich_iceberg(ib_raw, idx)
            enriched["positions"] = positions[-20:]
            enriched.update(_freshness_tag(True))
            return enriched

        # Iceberg not found in real data
        return offline_response("icebergs",
            f"Iceberg '{iceberg_name}' not found in NIC database.")

    # LIVE gate
    gate = check_or_offline("icebergs", False,
        "NIC iceberg data not yet available.")
    if gate is not None:
        return gate

    return _get_demo_iceberg_detail(iceberg_name)


def _get_demo_iceberg_detail(iceberg_name: str):
    from app.services.demo_service import get_iceberg_detail as _demo_det
    result = _demo_det(iceberg_name)
    if result:
        result.update(_freshness_tag(False))
    return result


def get_trajectory(iceberg_name: str, horizon_hours: int = 72):
    from app.services.demo_service import get_iceberg_trajectory as _demo_traj
    real, error = _get_real_icebergs()
    is_real = bool(real) and any(r.get("iceberg_name") == iceberg_name for r in real)

    # If real source has the iceberg, use real position + physics trajectory
    if is_real:
        ib_raw = next(r for r in real if r.get("iceberg_name") == iceberg_name)
        lat = ib_raw["latitude"]
        lon = ib_raw["longitude"]
        result = _build_trajectory(iceberg_name, lat, lon, horizon_hours)
        result["is_real_position"] = True
        result.update(_freshness_tag(True))
        return result

    gate = check_or_offline("icebergs", False,
        f"Iceberg '{iceberg_name}' not in NIC database.")
    if gate is not None:
        return gate

    result = _demo_traj(iceberg_name, horizon_hours)
    if result:
        result.update(_freshness_tag(False))
    return result


def _build_trajectory(iceberg_name: str, lat: float, lon: float,
                       horizon_hours: int) -> dict:
    from app.services.demo_service import _iceberg_drift, haversine_km
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    trajectory = []
    for h in [1, 6, 12, 24, 48, 72]:
        if h <= horizon_hours:
            pl, po, spd, dirn = _iceberg_drift(lat, lon, h,
                                                hash(iceberg_name + str(h)) % 99991)
            trajectory.append({
                "horizon_hours": h,
                "valid_time": (now + timedelta(hours=h)).isoformat(),
                "latitude": round(pl, 4), "longitude": round(po, 4),
                "uncertainty_km": round(2.0 + h / 72.0 * 25.0, 1),
                "confidence": round(max(0.45, 1.0 - h / 168.0 * 0.6), 3),
            })
    vessel_lat, vessel_lon = -65.0, -60.0  # use as reference point
    ca_km = None
    ca_time = None
    for tp in trajectory:
        d = haversine_km(tp["latitude"], tp["longitude"], vessel_lat, vessel_lon)
        if ca_km is None or d < ca_km:
            ca_km = round(d, 1)
            ca_time = tp["valid_time"]
    return {
        "iceberg_id": f"nic-{iceberg_name.lower().replace(' ', '-')}",
        "iceberg_name": iceberg_name,
        "current_lat": lat, "current_lon": lon,
        "predicted_at": now.isoformat(),
        "trajectory": trajectory,
        "model_name": "physics_drift_v1",
        "model_note": "Physics drift model. Not a certified ice drift forecast.",
        "closest_approach_km": ca_km,
        "closest_approach_time": ca_time,
        "data_mode": "live",
    }


def detect_icebergs():
    real, error = _get_real_icebergs()
    has_real = bool(real)

    gate = check_or_offline("icebergs", has_real)
    if gate is not None:
        return gate

    source_list = real if has_real else []
    if not has_real:
        from app.services.demo_service import get_icebergs as _d
        source_list = _d()["icebergs"]

    return {
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "method": "nic_tracking" if has_real else "demo",
        "detections": [
            {
                "iceberg_name": ic.get("iceberg_name", "?"),
                "latitude": ic.get("latitude"),
                "longitude": ic.get("longitude"),
                "estimated_area_km2": ic.get("area_km2"),
                "confidence": 1.0 if has_real else 0.87,
                "source": "US National Ice Center" if has_real else "demo",
            }
            for ic in source_list[:25]
        ],
        **_freshness_tag(has_real),
        "note": None if has_real else "DEMO DATA — positions are synthetic",
    }


def predict_trajectory(request):
    from datetime import timedelta
    from app.services.demo_service import _iceberg_drift
    now = datetime.now(timezone.utc)
    lat, lon = request.latitude, request.longitude
    trajectory = []
    for h in [1, 6, 12, 24, 48, 72]:
        if h <= request.horizon_hours:
            pl, po, spd, dirn = _iceberg_drift(
                lat, lon, h, hash(str(lat) + str(lon) + str(h)) % 99991)
            trajectory.append({
                "horizon_hours": h,
                "valid_time": (now + timedelta(hours=h)).isoformat(),
                "latitude": round(pl, 4), "longitude": round(po, 4),
                "uncertainty_km": round(2.0 + h / 72.0 * 25.0, 1),
                "confidence": round(max(0.45, 1.0 - h / 168.0 * 0.6), 3),
            })
    return {
        "iceberg_id": "custom",
        "iceberg_name": request.iceberg_name or "Custom Point",
        "current_lat": lat, "current_lon": lon,
        "predicted_at": now.isoformat(),
        "trajectory": trajectory,
        "model_name": "physics_drift_v1",
        "model_note": "Physics drift model only.",
        "closest_approach_km": None, "closest_approach_time": None,
        "data_mode": "live" if allow_demo_fallback() is False else "demo",
    }
