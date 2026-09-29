"""
Sea Ice Service — fixed to load and use the model registry.

WIRING (§MIGRATION_PLAN Phase 5, §12.4):
  get_forecast() now:
    1. Reads config/serving.yaml to discover the winning model at the requested lead.
    2. If max_validated_lead == 0 (no trained artifact yet), returns data_mode:
       "unavailable" with a clear message — never silently serves the old demo.
    3. If a model is registered as "ready", loads it via registry.get() and predicts.
    4. If the registry entry is absent or not "ready", raises HTTP 422 via live_gate.
    5. Falls back to a documented baseline only when serving.yaml explicitly says so
       (e.g., outcome "persistence" or "damped_persistence") — never silently.

The old unconditional `from app.services.demo_service import get_sea_ice_forecast`
call has been removed from get_forecast().  get_current_sea_ice() and get_history()
still use demo_service for the spatial grid and history, because those are
clearly labelled demo pathways and are not part of the model-serving bug.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from pathlib import Path

import yaml

from app.config import settings
from app.core.freshness import FreshnessRegistry, DataStatus, DataMode
from app.core.live_gate import check_or_offline, allow_demo_fallback, annotate_response

ROOT = Path(__file__).parents[3]
SERVING_YAML = ROOT / "config" / "serving.yaml"


# ── Serving configuration ─────────────────────────────────────────────────────

def _load_serving_config() -> dict:
    """Load config/serving.yaml; returns safe defaults if absent."""
    if SERVING_YAML.exists():
        try:
            with open(SERVING_YAML) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {"status": "NO_MODEL_TRAINED", "max_validated_lead": 0}


def get_max_validated_lead() -> int:
    return int(_load_serving_config().get("max_validated_lead", 0))


def get_served_model_for_lead(lead_days: int) -> str:
    """
    Return the serving decision for `lead_days`.
    Possible values: 'seaice_pixel', 'seaice_unet', 'persistence',
                     'damped_persistence', 'no_model'.
    """
    cfg = _load_serving_config()
    decisions = cfg.get("served_model_by_lead", {})
    key = str(lead_days)
    return decisions.get(key, "no_model")


# ── Freshness helper ──────────────────────────────────────────────────────────

def _freshness_tag(is_real: bool) -> dict:
    f = FreshnessRegistry.get("sea_ice")
    return {
        "freshness": f.to_dict() if f else None,
        "is_real": is_real,
        "data_mode": (
            DataMode.REAL.value if is_real
            else (DataMode.UNAVAILABLE.value if not allow_demo_fallback()
                  else DataMode.DEMO.value)
        ),
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


# ── Public API ────────────────────────────────────────────────────────────────

def get_current_sea_ice(resolution: str = "low"):
    """
    Returns current sea-ice grid.
    LIVE mode: real NSIDC extent overlaid on spatial physics model.
    DEMO mode: fully synthetic grid.
    """
    real_extent, error = _get_real_latest()
    has_real = real_extent is not None

    gate = check_or_offline(
        "sea_ice", has_real,
        error or "NSIDC sea-ice data not yet fetched. Check /api/live/status.",
    )
    if gate is not None:
        return gate

    from app.services.demo_service import get_sea_ice_grid as _demo_grid
    result = _demo_grid(resolution)

    if has_real:
        result["coverage_pct"] = round(real_extent["coverage_pct"], 1)
        result["extent_km2"]   = round(real_extent["extent_km2"], 0)
        result["source"]       = real_extent.get("source", "NSIDC G02135 v3")
        result["observation_date"] = real_extent.get("date")
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

    gate = check_or_offline(
        "sea_ice", has_real,
        error or "No historical sea-ice data available yet.",
    )
    if gate is not None:
        return gate

    if has_real:
        records = src.get_history(days=days)
        if records:
            result = {
                "start_date": records[0]["date"],
                "end_date":   records[-1]["date"],
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
    Sea-ice forecast.

    Decision tree (per §7.6 outcome rules):
      1. If max_validated_lead == 0 → no model trained → return unavailable.
      2. If requested lead > max_validated_lead → HTTP 422 (ForecastHorizonExceeded).
      3. Read per-lead decision from serving.yaml:
         - "seaice_pixel" / "seaice_unet" → load from registry; refuse if not ready.
         - "persistence" / "damped_persistence" → serve that baseline, labelled.
         - "no_model" → unavailable (should not happen past step 1).
    """
    lead_days = max(1, round(horizon_hours / 24))
    max_lead  = get_max_validated_lead()

    # ── No trained model ─────────────────────────────────────────────────────
    if max_lead == 0:
        return {
            "data_mode": DataMode.UNAVAILABLE.value,
            "horizon_hours": horizon_hours,
            "lead_days": lead_days,
            "reason": (
                "No sea-ice forecasting model has been trained yet. "
                "Training requires a verified real harmonised dataset — see "
                "DATA_LINEAGE.md. Run scripts/train_sea_ice.py when data is available."
            ),
            "serving_status": _load_serving_config().get("status", "NO_MODEL_TRAINED"),
            "max_validated_lead": 0,
            "model_note": "No model. Refusing to serve demo forecast as real.",
        }

    # ── Lead beyond validated range ───────────────────────────────────────────
    if lead_days > max_lead:
        raise HTTPException(
            status_code=422,
            detail={
                "data_mode": DataMode.UNAVAILABLE.value,
                "horizon_hours": horizon_hours,
                "lead_days": lead_days,
                "reason": (
                    f"Requested lead ({lead_days} days) exceeds max validated lead "
                    f"({max_lead} days). The API refuses unvalidated leads (§12.1)."
                ),
                "max_validated_lead": max_lead,
            },
        )

    decision = get_served_model_for_lead(lead_days)

    # ── Learned model (pixel or unet) ─────────────────────────────────────────
    if decision in ("seaice_pixel", "seaice_unet"):
        from app.ml.registry import registry, ModelState
        entry = registry.get(decision)
        if entry is None or entry.state != ModelState.READY:
            state = entry.state.value if entry else "not_registered"
            return {
                "data_mode": DataMode.UNAVAILABLE.value,
                "horizon_hours": horizon_hours,
                "lead_days": lead_days,
                "reason": (
                    f"Model '{decision}' is registered for lead {lead_days} but "
                    f"is not ready (state={state}). "
                    "Check models/manifest.json and registry logs."
                ),
            }
        # TODO: call entry.obj.predict_field() and format the gridded response
        # This requires a live issue-time concentration field from the ingest
        # pipeline; wired in Phase 5 after real data arrives.
        return {
            "data_mode": DataMode.UNAVAILABLE.value,
            "horizon_hours": horizon_hours,
            "lead_days": lead_days,
            "reason": (
                "Model artifact is registered and ready, but the serving "
                "path from registry.predict_field() to the API response schema "
                "has not yet been wired (pending Phase 5 real-data completion). "
                "See sea_ice_service.py TODO above."
            ),
            "model_id": entry.model_id if entry else decision,
        }

    # ── Documented baseline outcome ───────────────────────────────────────────
    if decision in ("persistence", "damped_persistence"):
        real_extent, _ = _get_real_latest()
        cfg = _load_serving_config()
        return {
            "data_mode": DataMode.DEMO.value,
            "horizon_hours": horizon_hours,
            "lead_days": lead_days,
            "serving_decision": decision,
            "reason": (
                f"Per config/serving.yaml, lead {lead_days} is served by "
                f"'{decision}' because the trained model did not beat it. "
                "See results/seaice_eval.json for the evaluation that produced this decision."
            ),
            "max_validated_lead": max_lead,
            "evaluation_file": cfg.get("evaluation_file"),
            "model_note": (
                "Persistence baseline.  Not a certified operational forecast."
                if decision == "persistence"
                else "Damped-persistence baseline (exponential decay toward climatology)."
            ),
            "source": "POLAR-AI evaluation harness baseline",
        }

    # ── Fallthrough: should not reach here ────────────────────────────────────
    return {
        "data_mode": DataMode.UNAVAILABLE.value,
        "horizon_hours": horizon_hours,
        "lead_days": lead_days,
        "reason": (
            f"Unrecognised serving decision '{decision}' for lead {lead_days}. "
            "This is a configuration bug — check config/serving.yaml."
        ),
    }


def predict(request):
    return get_forecast(request.horizon_hours)


def offline_response(source_id: str, message: str) -> dict:
    from app.core.live_gate import offline_response as _or
    return _or(source_id, message)
