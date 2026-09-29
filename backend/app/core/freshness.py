"""
POLAR-AI Data Freshness Engine
==============================
Every data layer reports its status honestly.

Status hierarchy:
  LIVE            → data is from a real-time source, age < threshold
  NEAR_REAL_TIME  → real source, age within expected update cycle
  LATEST_AVAILABLE→ real source, possibly delayed but most recent available
  STALE           → real source but beyond expected freshness threshold
  OFFLINE         → real source configured but currently unreachable
  DEMO            → synthetic / seed-based data (no real source)

RULE: The backend determines status. The frontend never guesses.
RULE: Never label DEMO data as LIVE.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


class DataMode(str, Enum):
    REAL = "real"
    DEMO = "demo"
    UNAVAILABLE = "unavailable"
    LIVE = "live"


class DataStatus(str, Enum):
    LIVE = "LIVE"
    NEAR_REAL_TIME = "NEAR_REAL_TIME"
    LATEST_AVAILABLE = "LATEST_AVAILABLE"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    DEMO = "DEMO"
    UNKNOWN = "UNKNOWN"


# Human-readable display labels
STATUS_LABELS = {
    DataStatus.LIVE: "LIVE",
    DataStatus.NEAR_REAL_TIME: "NEAR REAL-TIME",
    DataStatus.LATEST_AVAILABLE: "LATEST AVAILABLE",
    DataStatus.STALE: "STALE",
    DataStatus.OFFLINE: "OFFLINE",
    DataStatus.DEMO: "DEMO",
    DataStatus.UNKNOWN: "UNKNOWN",
}

STATUS_COLORS = {
    DataStatus.LIVE: "green",
    DataStatus.NEAR_REAL_TIME: "green",
    DataStatus.LATEST_AVAILABLE: "yellow",
    DataStatus.STALE: "orange",
    DataStatus.OFFLINE: "red",
    DataStatus.DEMO: "amber",
    DataStatus.UNKNOWN: "gray",
}


@dataclass
class FreshnessInfo:
    """Complete freshness metadata for one data layer."""
    source_id: str                          # e.g. "ais", "sea_ice", "satellite"
    source_name: str                        # human label
    status: DataStatus = DataStatus.UNKNOWN
    last_updated: Optional[datetime] = None
    last_attempted: Optional[datetime] = None
    last_error: Optional[str] = None
    age_seconds: Optional[float] = None
    mode: str = DataMode.DEMO.value
    source: str = ""                        # provider name
    record_count: Optional[int] = None
    error_count: int = 0
    is_real: bool = False

    def to_dict(self) -> dict:
        age_s = self.age_seconds
        if age_s is None and self.last_updated:
            age_s = (datetime.now(timezone.utc) - self.last_updated).total_seconds()

        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "status": self.status.value,
            "status_label": STATUS_LABELS[self.status],
            "status_color": STATUS_COLORS[self.status],
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "last_attempted": self.last_attempted.isoformat() if self.last_attempted else None,
            "last_error": self.last_error,
            "age_seconds": round(age_s, 1) if age_s is not None else None,
            "age_human": _human_age(age_s) if age_s is not None else "unknown",
            "mode": self.mode,
            "data_mode": self.mode,
            "source": self.source,
            "record_count": self.record_count,
            "error_count": self.error_count,
            "is_real": self.is_real,
        }


def _human_age(seconds: float) -> str:
    """Convert seconds to human-readable age string."""
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def compute_status(
    last_updated: Optional[datetime],
    is_real: bool,
    stale_threshold_s: int,
    nrt_threshold_s: int = None,
    is_offline: bool = False,
) -> DataStatus:
    """
    Compute freshness status from timestamps and configuration.

    Args:
        last_updated: When data was last successfully fetched
        is_real: Whether this is a real (non-demo) source
        stale_threshold_s: Age in seconds beyond which data is STALE
        nrt_threshold_s: Age in seconds to qualify as NEAR_REAL_TIME (default = stale/4)
        is_offline: True if the source returned an error on last attempt
    """
    if not is_real:
        return DataStatus.DEMO

    if is_offline:
        return DataStatus.OFFLINE

    if last_updated is None:
        return DataStatus.OFFLINE

    age_s = (datetime.now(timezone.utc) - last_updated).total_seconds()

    if nrt_threshold_s is None:
        nrt_threshold_s = stale_threshold_s // 4

    if age_s > stale_threshold_s:
        return DataStatus.STALE
    if age_s > nrt_threshold_s:
        return DataStatus.LATEST_AVAILABLE
    # Very fresh — NEAR_REAL_TIME unless explicitly marked LIVE
    return DataStatus.NEAR_REAL_TIME


# ── Global freshness registry ──────────────────────────────────────────────────
# Each data layer registers itself here so the system status endpoint can
# aggregate everything in one call.

class FreshnessRegistry:
    """
    Thread-safe (GIL-protected for CPython) in-memory registry.
    Each data layer updates its FreshnessInfo here whenever it fetches data.
    """
    _store: dict[str, FreshnessInfo] = {}

    @classmethod
    def register(cls, info: FreshnessInfo):
        cls._store[info.source_id] = info

    @classmethod
    def update(
        cls,
        source_id: str,
        *,
        last_updated: Optional[datetime] = None,
        last_error: Optional[str] = None,
        status: Optional[DataStatus] = None,
        record_count: Optional[int] = None,
        last_attempted: Optional[datetime] = None,
    ):
        """Update fields for an existing registered source."""
        if source_id not in cls._store:
            return
        info = cls._store[source_id]
        now = datetime.now(timezone.utc)
        if last_attempted is not None:
            info.last_attempted = last_attempted
        else:
            info.last_attempted = now
        if last_updated is not None:
            info.last_updated = last_updated
            info.last_error = None
            info.age_seconds = 0.0
        if last_error is not None:
            info.last_error = last_error
            info.error_count += 1
        if status is not None:
            info.status = status
        if record_count is not None:
            info.record_count = record_count

    @classmethod
    def get(cls, source_id: str) -> Optional[FreshnessInfo]:
        return cls._store.get(source_id)

    @classmethod
    def get_all(cls) -> list[FreshnessInfo]:
        return list(cls._store.values())

    @classmethod
    def summary(cls) -> dict:
        all_info = cls.get_all()
        live_count = sum(1 for i in all_info if i.status == DataStatus.LIVE)
        nrt_count = sum(1 for i in all_info if i.status == DataStatus.NEAR_REAL_TIME)
        demo_count = sum(1 for i in all_info if i.mode == DataMode.DEMO.value)
        unavailable_count = sum(1 for i in all_info if i.mode == DataMode.UNAVAILABLE.value)
        return {
            "total": len(all_info),
            "live": live_count,
            "near_real_time": nrt_count,
            "demo": demo_count,
            "offline": unavailable_count,
            "unavailable": unavailable_count,
            "sources": [i.to_dict() for i in all_info],
        }


# ── Pre-register all data sources ─────────────────────────────────────────────
def init_freshness_registry(settings):
    """
    Pre-populate the freshness registry at startup.

    Correct classification of free vs credentialed sources:
      - weather:  Open-Meteo NWP  → always real, no credentials needed
      - ocean:    Open-Meteo Marine → always real, no credentials needed
      - icebergs: NIC CSV          → always real, free public HTTP
      - sea_ice:  NSIDC daily CSV  → always real, free public HTTP
      - satellite: Copernicus      → needs COPERNICUS_CLIENT_ID/SECRET
      - ais:       AIS provider    → needs AIS_PROVIDER + AIS_API_KEY
    """
    from app.core.freshness import FreshnessRegistry, FreshnessInfo, DataStatus

    is_demo_mode = settings.DATA_MODE.lower() == "demo"

    sources = [
        FreshnessInfo(
            source_id="ais",
            source_name="AIS Vessel Tracking",
            # AIS needs credentials. In demo mode: DEMO. No creds in live: OFFLINE.
            status=(DataStatus.DEMO if is_demo_mode
                    else (DataStatus.OFFLINE if not settings.has_ais
                          else DataStatus.OFFLINE)),  # will be updated on first fetch
            mode="demo" if is_demo_mode else "live",
            source=settings.AIS_PROVIDER if settings.has_ais else ("demo" if is_demo_mode else "not_configured"),
            is_real=settings.has_ais and not is_demo_mode,
        ),
        FreshnessInfo(
            source_id="satellite",
            source_name="Sentinel-1 SAR",
            status=(DataStatus.DEMO if is_demo_mode
                    else (DataStatus.OFFLINE if not settings.has_copernicus
                          else DataStatus.OFFLINE)),
            mode="demo" if is_demo_mode else "live",
            source="Copernicus Data Space" if settings.has_copernicus else "not_configured",
            is_real=settings.has_copernicus and not is_demo_mode,
        ),
        FreshnessInfo(
            source_id="sea_ice",
            source_name="Sea Ice — NSIDC",
            # NSIDC daily CSV is free. In demo mode: DEMO. Otherwise: OFFLINE until fetched.
            status=DataStatus.DEMO if is_demo_mode else DataStatus.OFFLINE,
            mode="demo" if is_demo_mode else "live",
            source="NSIDC Sea Ice Index G02135 v3 (free)",
            is_real=not is_demo_mode,
        ),
        FreshnessInfo(
            source_id="icebergs",
            source_name="Iceberg Tracking — NIC",
            status=DataStatus.DEMO if is_demo_mode else DataStatus.OFFLINE,
            mode="demo" if is_demo_mode else "live",
            source="US National Ice Center (free)",
            is_real=not is_demo_mode,
        ),
        FreshnessInfo(
            source_id="weather",
            # Open-Meteo is free — always real, no credentials needed
            source_name="Weather — Open-Meteo NWP",
            status=DataStatus.DEMO if is_demo_mode else DataStatus.OFFLINE,
            mode="demo" if is_demo_mode else "live",
            source="Open-Meteo NWP (free, no credentials)",
            is_real=not is_demo_mode,
        ),
        FreshnessInfo(
            source_id="ocean",
            # Open-Meteo Marine is free — always real
            source_name="Ocean — Open-Meteo Marine",
            status=DataStatus.DEMO if is_demo_mode else DataStatus.OFFLINE,
            mode="demo" if is_demo_mode else "live",
            source="Open-Meteo Marine (free, no credentials)",
            is_real=not is_demo_mode,
        ),
        FreshnessInfo(
            source_id="database",
            source_name="PostgreSQL / PostGIS",
            status=DataStatus.UNKNOWN,
            mode="live",
            source="local",
            is_real=True,
        ),
    ]
    for s in sources:
        FreshnessRegistry.register(s)
