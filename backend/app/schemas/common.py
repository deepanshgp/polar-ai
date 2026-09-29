"""Common Pydantic schemas used across POLAR-AI."""
from pydantic import BaseModel
from app.core.freshness import DataMode
from typing import Optional, Any, Dict
from datetime import datetime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    database: str
    postgis: bool
    data_mode: DataMode
    llm_available: bool
    llm_provider: str


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class BoundingBox(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class DashboardStats(BaseModel):
    sea_ice_coverage_pct: float
    active_icebergs: int
    current_risk_score: float
    current_risk_category: str
    vessel_status: str
    vessel_lat: float
    vessel_lon: float
    data_mode: DataMode
    last_updated: datetime


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: int = 400
