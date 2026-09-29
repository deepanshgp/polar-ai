"""
POLAR-AI LiveDataGate
=====================
Single function called by every service before returning demo data.

Rules:
  DATA_MODE=live  → NEVER return demo data. Return an OFFLINE response.
  DATA_MODE=demo  → Always return demo data (explicit test/demo mode).
  DATA_MODE=auto  → Return demo only when real source has no data yet.
                    Once real data is available, use it.

OFFLINE response format — what services return instead of fake data:
{
    "status": "OFFLINE",
    "source_id": "sea_ice",
    "message": "No real data available. Source: NSIDC — not yet fetched.",
    "last_successful_update": null | ISO timestamp,
    "data_mode": "offline",
    "is_real": False,
}

This guarantees the frontend never silently shows fake data in LIVE mode.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.config import settings
from app.core.freshness import FreshnessRegistry
from app.core.freshness import DataMode


def is_live_mode() -> bool:
    """True when the application must use real data only."""
    return settings.effective_data_mode == "live"


def is_demo_mode() -> bool:
    return settings.DATA_MODE.lower() == "demo"


def allow_demo_fallback() -> bool:
    """True when demo fallback is acceptable (auto or demo mode)."""
    return not is_live_mode()


DEFAULT_SOURCE_PAYLOADS: Dict[str, Dict[str, Any]] = {
    "sea_ice": {
        "grid_points": [],
        "coverage_pct": 0.0,
        "extent_km2": 0.0,
        "data_points": [],
        "source": "unavailable",
    },
    "icebergs": {
        "icebergs": [],
        "total_count": 0,
        "active_count": 0,
        "high_risk_count": 0,
        "positions": [],
        "trajectory": [],
        "source": "unavailable",
    },
    "weather": {
        "grid_points": [],
        "source": "unavailable",
    },
    "ocean": {
        "grid_points": [],
        "source": "unavailable",
    },
}


def offline_response(
    source_id: str,
    message: str = None,
    last_updated: Optional[datetime] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build an OFFLINE response to return instead of demo data in LIVE mode.
    Every service uses this when real data is unavailable.
    """
    freshness = FreshnessRegistry.get(source_id)
    last_ok = last_updated
    if last_ok is None and freshness and freshness.last_updated:
        last_ok = freshness.last_updated

    payload = dict(DEFAULT_SOURCE_PAYLOADS.get(source_id, {}))
    if extra_fields:
        payload.update(extra_fields)

    payload.update({
        "status": "OFFLINE",
        "source_id": source_id,
        "message": message or (
            f"No real data available for '{source_id}'. "
            f"Data will appear once the source is connected."
        ),
        "last_successful_update": last_ok.isoformat() if last_ok else None,
        "last_error": freshness.last_error if freshness else None,
        "data_mode": DataMode.UNAVAILABLE.value,
        "is_real": False,
        "reason": message or "Real source unavailable or failed validation.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return payload


def check_or_offline(source_id: str, has_data: bool, message: str = None) -> Optional[Dict]:
    """
    Call at the top of every service function that might fall back to demo.

    Returns:
        None  → caller should proceed (real data available, or demo allowed)
        Dict  → caller must return this OFFLINE dict to the endpoint

    Usage in a service:
        gate = check_or_offline("sea_ice", bool(real_data))
        if gate is not None:
            return gate
        # ... use real_data ...
    """
    if has_data:
        return None  # real data exists — proceed

    if allow_demo_fallback():
        return None  # demo fallback is allowed — proceed

    # LIVE mode, no real data → return OFFLINE
    return offline_response(source_id, message)


def annotate_response(response: Dict, source_id: str, is_real: bool) -> Dict:
    """
    Add standardised freshness metadata to any service response dict.
    Every API response must carry these fields.
    """
    freshness = FreshnessRegistry.get(source_id)
    response["_meta"] = {
        "source_id": source_id,
        "is_real": is_real,
        "data_mode": DataMode.REAL.value if is_real else (DataMode.UNAVAILABLE.value if is_live_mode() else DataMode.DEMO.value),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": freshness.last_updated.isoformat() if (freshness and freshness.last_updated) else None,
        "age_seconds": freshness.to_dict().get("age_seconds") if freshness else None,
        "status": freshness.status.value if freshness else "UNKNOWN",
        "status_label": freshness.to_dict().get("status_label") if freshness else "UNKNOWN",
    }
    return response
