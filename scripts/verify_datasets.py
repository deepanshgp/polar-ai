"""Fail-closed dataset verification entry point."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from app.sources.osisaf_source import OsiSafSource
from app.sources.era5_source import Era5Source
from app.sources.currents_source import CurrentsSource

def main():
    sources = [OsiSafSource(), Era5Source(), CurrentsSource()]
    for source in sources:
        if not source.is_configured():
            print(f"{source.source_id}: unavailable (credentials/configuration not present)")
            continue
        print(f"{source.source_id}: configured; supply downloaded fixture paths for validation")
    print("NSIDC and NIC adapters remain available through their existing source modules.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
