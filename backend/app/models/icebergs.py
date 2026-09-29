"""
POLAR-AI Iceberg Models
Database tables for icebergs and their trajectories.
"""
from sqlalchemy import Column, Float, Integer, String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
import uuid
from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Iceberg(Base, UUIDMixin, TimestampMixin):
    """
    Master record for a tracked iceberg.
    """
    __tablename__ = "icebergs"

    # Official iceberg designation (e.g., "A-76", "B-22")
    iceberg_name = Column(String(50), nullable=False, unique=True, index=True)

    # Source of detection
    source = Column(String(100), default="demo")  # nic | byu | detection | demo

    # Current/latest known position
    last_known_lat = Column(Float)
    last_known_lon = Column(Float)
    last_known_location = Column(Geometry("POINT", srid=4326))
    last_observed_at = Column(DateTime(timezone=True))

    # Physical dimensions
    length_km = Column(Float)   # major axis in km
    width_km = Column(Float)    # minor axis in km
    area_km2 = Column(Float)    # estimated area

    # Status
    status = Column(String(30), default="active")  # active | grounded | disintegrated | lost
    is_active = Column(Boolean, default=True)

    # Drift characteristics
    drift_speed_kmh = Column(Float)       # estimated speed
    drift_direction_deg = Column(Float)   # heading in degrees (0-360)

    # Risk assessment
    risk_level = Column(String(20), default="low")  # low | medium | high | critical
    threat_to_vessel = Column(Boolean, default=False)

    # Metadata
    data_mode = Column(String(10), default="demo")

    # Relationships
    positions = relationship("IcebergPosition", back_populates="iceberg", order_by="IcebergPosition.observed_at")
    trajectory_predictions = relationship("IcebergTrajectoryPrediction", back_populates="iceberg")


class IcebergPosition(Base, UUIDMixin, TimestampMixin):
    """
    Historical position record for a tracked iceberg.
    Multiple positions form the observed trajectory.
    """
    __tablename__ = "iceberg_positions"

    iceberg_id = Column(UUID(as_uuid=True), ForeignKey("icebergs.id"), nullable=False, index=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location = Column(Geometry("POINT", srid=4326))

    # Physical state at this observation
    length_km = Column(Float)
    width_km = Column(Float)
    area_km2 = Column(Float)

    # Computed motion
    speed_kmh = Column(Float)
    direction_deg = Column(Float)

    # Source of observation
    source = Column(String(50), default="demo")
    source_kind = Column(String(20), default="live", nullable=False)  # historical | live
    confidence = Column(Float, default=1.0)  # 0.0 - 1.0

    iceberg = relationship("Iceberg", back_populates="positions")


class IcebergTrajectoryPrediction(Base, UUIDMixin, TimestampMixin):
    """
    ML/physics-predicted future trajectory for an iceberg.
    """
    __tablename__ = "iceberg_trajectory_predictions"

    iceberg_id = Column(UUID(as_uuid=True), ForeignKey("icebergs.id"), nullable=False, index=True)

    # When prediction was generated
    predicted_at = Column(DateTime(timezone=True), nullable=False)
    # What time this position is predicted for
    valid_time = Column(DateTime(timezone=True), nullable=False)
    horizon_hours = Column(Integer, nullable=False)  # 1, 6, 12, 24, 48, 72

    predicted_lat = Column(Float, nullable=False)
    predicted_lon = Column(Float, nullable=False)
    predicted_location = Column(Geometry("POINT", srid=4326))

    # Uncertainty ellipse (semi-axes in km)
    uncertainty_major_km = Column(Float)
    uncertainty_minor_km = Column(Float)
    uncertainty_bearing_deg = Column(Float)

    confidence = Column(Float)  # 0.0 - 1.0
    model_name = Column(String(50), default="physics_baseline")

    iceberg = relationship("Iceberg", back_populates="trajectory_predictions")
