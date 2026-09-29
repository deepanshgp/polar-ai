"""BYU consolidated historical iceberg positions, kept separate from NIC live data."""
from datetime import datetime, timezone
from pathlib import Path
import csv

class ByuHistoricalSource:
    source_id = "byu_icebergs_historical"
    def is_configured(self): return True
    def fetch(self, start, end, cfg=None): raise RuntimeError("BYU download URL must be selected from the published dataset release")
    def load(self, paths):
        records = []
        for path in paths:
            with open(path, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    try:
                        lat = float(row.get("lat") or row.get("latitude")); lon = ((float(row.get("lon") or row.get("longitude")) + 180) % 360) - 180
                        records.append({"berg_id": row.get("berg_id") or row.get("iceberg_id") or row.get("name"), "timestamp": datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc) if datetime.fromisoformat(row["timestamp"]).tzinfo is None else datetime.fromisoformat(row["timestamp"]), "lon": lon, "lat": lat, "source_sensor": row.get("source_sensor", "unknown"), "quality_flag": row.get("quality_flag")})
                    except (KeyError, TypeError, ValueError): continue
        return records
    def validate(self, records):
        errors=[]
        for r in records:
            if not r["berg_id"] or not (-90 <= r["lat"] <= -45) or not (-180 <= r["lon"] <= 180): errors.append(r)
        return errors
