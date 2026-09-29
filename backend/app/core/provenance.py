"""Provenance metadata carried with every real data product."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Provenance:
    source: str
    product_id: str
    variable: str
    units: str
    valid_time: datetime
    retrieved_at: datetime
    resolution_m: Optional[float]
    native_grid: str
    notes: Optional[str] = None

