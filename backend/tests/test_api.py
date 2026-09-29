"""
POLAR-AI Backend API Tests
Tests core API endpoints, services, and algorithms.
"""
import pytest
import math
from fastapi.testclient import TestClient

# Use TestClient (sync) for simplicity
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

client = TestClient(app)


# ── Health ────────────────────────────────────────────────────────────────────

def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert data["version"] == "1.0.0"


def test_root_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "POLAR-AI"
    assert "sih_problem" in data


# ── Dashboard ─────────────────────────────────────────────────────────────────

def test_dashboard():
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "sea_ice_coverage_pct" in data
    assert "active_icebergs" in data
    assert "current_risk_score" in data
    assert 0 <= data["sea_ice_coverage_pct"] <= 100
    assert data["active_icebergs"] >= 0
    assert 0 <= data["current_risk_score"] <= 100
    # data_mode can be 'demo' in test context or 'live' in production
    assert data.get("data_mode") in ("demo", "live", None) or "effective_data_mode" in data


# ── Sea Ice ───────────────────────────────────────────────────────────────────

def test_sea_ice_current():
    resp = client.get("/api/sea-ice/current")
    assert resp.status_code == 200
    data = resp.json()
    assert "grid_points" in data
    assert len(data["grid_points"]) > 0
    assert "coverage_pct" in data
    assert 0 <= data["coverage_pct"] <= 100
    # Check a grid point structure
    gp = data["grid_points"][0]
    assert "latitude" in gp
    assert "longitude" in gp
    assert "concentration" in gp
    assert 0 <= gp["concentration"] <= 1
    assert "ice_category" in gp
    assert gp["ice_category"] in ["open_water", "low", "moderate", "high", "consolidated"]


def test_sea_ice_current_resolution():
    for res in ["low", "medium", "high"]:
        resp = client.get(f"/api/sea-ice/current?resolution={res}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["grid_points"]) > 0


def test_sea_ice_history():
    resp = client.get("/api/sea-ice/history?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "data_points" in data
    assert len(data["data_points"]) >= 30
    for dp in data["data_points"]:
        assert "date" in dp
        assert "coverage_pct" in dp
        assert 0 <= dp["coverage_pct"] <= 100


def test_sea_ice_forecast():
    resp = client.get("/api/sea-ice/forecast?horizon_hours=72")
    assert resp.status_code == 200
    data = resp.json()
    assert "horizon_hours" in data
    assert data["horizon_hours"] == 72
    if data.get("data_mode") == "unavailable":
        assert "reason" in data
        assert "max_validated_lead" in data
    else:
        assert "grid_points" in data
        assert "overall_confidence" in data
        assert 0 <= data["overall_confidence"] <= 1


def test_sea_ice_predict():
    resp = client.post("/api/sea-ice/predict", json={"horizon_hours": 48})
    assert resp.status_code == 200


# ── Icebergs ──────────────────────────────────────────────────────────────────

def test_list_icebergs():
    resp = client.get("/api/icebergs")
    assert resp.status_code == 200
    data = resp.json()
    assert "icebergs" in data
    assert len(data["icebergs"]) > 0
    assert "total_count" in data
    assert "high_risk_count" in data
    # Check iceberg structure
    ib = data["icebergs"][0]
    assert "iceberg_name" in ib
    assert "latitude" in ib
    assert "longitude" in ib
    assert -90 <= ib["latitude"] <= 0  # Antarctic
    assert "risk_level" in ib
    assert ib["risk_level"] in ["low", "medium", "high", "critical"]
    assert data["data_mode"] == "demo"


def test_get_iceberg_detail():
    resp = client.get("/api/icebergs/A-76A")
    assert resp.status_code == 200
    data = resp.json()
    assert data["iceberg_name"] == "A-76A"
    assert "positions" in data
    assert len(data["positions"]) > 0


def test_get_iceberg_not_found():
    resp = client.get("/api/icebergs/NONEXISTENT-999")
    assert resp.status_code == 404


def test_get_iceberg_trajectory():
    resp = client.get("/api/icebergs/A-76A/trajectory?horizon_hours=72")
    assert resp.status_code == 200
    data = resp.json()
    assert "trajectory" in data
    assert len(data["trajectory"]) > 0
    for tp in data["trajectory"]:
        assert "horizon_hours" in tp
        assert "latitude" in tp
        assert "longitude" in tp
        assert "confidence" in tp
        assert 0 <= tp["confidence"] <= 1


# ── Weather ───────────────────────────────────────────────────────────────────

def test_weather_current():
    resp = client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()
    assert "grid_points" in data
    assert len(data["grid_points"]) > 0
    gp = data["grid_points"][0]
    assert "wind_speed_ms" in gp
    assert gp["wind_speed_ms"] >= 0
    assert "air_temp_celsius" in gp


def test_weather_forecast():
    resp = client.get("/api/weather/forecast?horizon_hours=48")
    assert resp.status_code == 200


def test_real_source_exception_is_unavailable(monkeypatch):
    from app.config import settings
    from app.services import weather_service

    monkeypatch.setattr(settings, "DATA_MODE", "live")
    monkeypatch.setattr(
        weather_service,
        "_get_real_grid",
        lambda: ([], "simulated Open-Meteo connection failure"),
    )
    response = client.get("/api/weather/current")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "unavailable"
    assert payload["is_real"] is False
    assert payload["reason"]


# ── Ocean ─────────────────────────────────────────────────────────────────────

def test_ocean_current():
    resp = client.get("/api/ocean/current")
    assert resp.status_code == 200
    data = resp.json()
    assert "grid_points" in data
    gp = data["grid_points"][0]
    assert "current_speed_ms" in gp
    assert gp["current_speed_ms"] >= 0
    assert "sea_surface_temp_celsius" in gp


# ── Risk Engine ───────────────────────────────────────────────────────────────

def test_risk_calculate():
    resp = client.post("/api/risk/calculate", json={
        "latitude": -66.0,
        "longitude": -60.0,
        "radius_km": 50.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "total_risk_score" in data
    assert 0 <= data["total_risk_score"] <= 1
    assert "risk_category" in data
    assert data["risk_category"] in ["low", "moderate", "high", "extreme"]
    assert "sea_ice_risk" in data
    assert "iceberg_risk" in data
    assert "weather_risk" in data
    assert "ocean_risk" in data
    assert "risk_factors" in data
    assert "recommendations" in data


def test_risk_weights_sum():
    """Risk component scores should be between 0 and 1."""
    resp = client.post("/api/risk/calculate", json={
        "latitude": -70.0,
        "longitude": 0.0,
        "radius_km": 100.0,
    })
    data = resp.json()
    for key in ["sea_ice_risk", "iceberg_risk", "weather_risk", "ocean_risk", "total_risk_score"]:
        assert 0 <= data[key] <= 1, f"{key} out of range: {data[key]}"


# ── Routes ────────────────────────────────────────────────────────────────────

def test_generate_routes():
    resp = client.post("/api/routes/generate", json={
        "origin_lat": -66.0,
        "origin_lon": -60.0,
        "origin_name": "Vessel Position",
        "destination_lat": -67.57,
        "destination_lon": -68.13,
        "destination_name": "Rothera Station",
        "generate_all": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "routes" in data
    assert len(data["routes"]) >= 1


def test_compare_routes():
    resp = client.post("/api/routes/compare", json={
        "origin_lat": -66.0,
        "origin_lon": -60.0,
        "destination_lat": -67.57,
        "destination_lon": -68.13,
        "origin_name": "McMurdo",
        "destination_name": "Rothera",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "routes" in data
    assert len(data["routes"]) == 4  # shortest, safest, fuel_efficient, balanced
    assert "recommended_route_type" in data
    assert "recommendation_reason" in data

    # Verify route structure
    for route in data["routes"]:
        assert "route_type" in route
        assert "total_distance_km" in route
        assert route["total_distance_km"] > 0
        assert "estimated_duration_hours" in route
        assert "estimated_fuel_tonnes" in route
        assert "overall_risk_score" in route
        assert 0 <= route["overall_risk_score"] <= 1
        assert "waypoints" in route
        assert len(route["waypoints"]) >= 2


def test_route_by_id():
    # First generate a route
    gen_resp = client.post("/api/routes/generate", json={
        "origin_lat": -66.0,
        "origin_lon": -60.0,
        "destination_lat": -67.57,
        "destination_lon": -68.13,
        "generate_all": False,
        "route_preference": "balanced",
    })
    routes = gen_resp.json()["routes"]
    assert len(routes) > 0
    route_id = routes[0]["id"]

    # Then fetch it by ID
    resp = client.get(f"/api/routes/{route_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == route_id


def test_route_not_found():
    resp = client.get("/api/routes/nonexistent-id-12345")
    assert resp.status_code == 404


# ── Analytics ─────────────────────────────────────────────────────────────────

def test_analytics():
    resp = client.get("/api/analytics?days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert "sea_ice_trend" in data
    assert "iceberg_count_trend" in data
    assert "forecast_accuracy" in data
    assert len(data["sea_ice_trend"]) >= 30


# ── Data Sources ──────────────────────────────────────────────────────────────

def test_data_sources():
    resp = client.get("/api/data-sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert len(data["sources"]) > 0
    assert "data_mode" in data


# ── AI Agent ─────────────────────────────────────────────────────────────────

def test_agent_query_route():
    resp = client.post("/api/agent/query", json={
        "query": "Which route is safest?",
        "context": {}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert len(data["response"]) > 0
    assert "tools_used" in data
    assert len(data["tools_used"]) > 0


def test_agent_query_icebergs():
    resp = client.post("/api/agent/query", json={
        "query": "Are there any dangerous icebergs nearby?",
        "context": {}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "iceberg" in data["response"].lower() or "berg" in data["response"].lower()


def test_agent_query_weather():
    resp = client.post("/api/agent/query", json={
        "query": "What are the current weather conditions?",
        "context": {}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data


def test_agent_query_vessel():
    resp = client.post("/api/agent/query", json={
        "query": "Where is the vessel?",
        "context": {}
    })
    assert resp.status_code == 200


# ── Simulation ────────────────────────────────────────────────────────────────

def test_simulation_state():
    resp = client.get("/api/simulation/state")
    assert resp.status_code == 200
    data = resp.json()
    assert "step" in data
    assert "vessel" in data
    assert "icebergs" in data
    assert "running" in data


def test_simulation_controls():
    client.post("/api/simulation/reset")
    resp = client.post("/api/simulation/start")
    assert resp.status_code == 200
    assert resp.json()["running"] is True

    resp = client.post("/api/simulation/pause")
    assert resp.status_code == 200
    assert resp.json()["running"] is False

    resp = client.post("/api/simulation/step")
    assert resp.status_code == 200
    assert resp.json()["step"] >= 0


# ── Demo Service Unit Tests ───────────────────────────────────────────────────

def test_sic_range():
    from app.services.demo_service import _sic_at
    for lat in [-80, -70, -60, -55]:
        for lon in [-180, -90, 0, 90, 180]:
            sic = _sic_at(lat, lon)
            assert 0 <= sic <= 1, f"SIC out of range at ({lat}, {lon}): {sic}"


def test_iceberg_drift_bounds():
    from app.services.demo_service import _iceberg_drift
    for lat in [-70, -65, -60]:
        new_lat, new_lon, speed, direction = _iceberg_drift(lat, -60.0, 24, 42)
        assert -80 <= new_lat <= -55
        assert -180 <= new_lon <= 180
        assert speed >= 0
        assert 0 <= direction <= 360


def test_haversine():
    from app.services.demo_service import haversine_km
    # McMurdo to Palmer: roughly 3750 km
    dist = haversine_km(-77.85, 166.67, -64.77, -64.05)
    assert 3500 < dist < 4200, f"McMurdo-Palmer distance unexpected: {dist}"


def test_a_star_route():
    from app.services.route_service import _astar, ROUTE_WEIGHTS
    wps = _astar(-66.0, -60.0, -67.57, -68.13, ROUTE_WEIGHTS["balanced"])
    assert len(wps) >= 2
    # Start and end should be close to requested points
    start = wps[0]
    end = wps[-1]
    assert abs(start[0] - (-66.0)) < 2.0
    assert abs(end[0] - (-67.57)) < 2.0
