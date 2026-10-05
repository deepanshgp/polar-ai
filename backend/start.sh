#!/bin/sh
# POLAR-AI backend startup script
set -e

echo "=== POLAR-AI Backend Startup ==="
echo "Data mode: ${DATA_MODE:-demo}"
echo "Database:  ${DATABASE_URL:-not set}"

# Run Alembic migrations (retries for DB readiness)
MAX_RETRIES=10
RETRY=0
until alembic upgrade head 2>/dev/null || [ $RETRY -ge $MAX_RETRIES ]; do
    RETRY=$((RETRY+1))
    echo "  Waiting for database... attempt $RETRY/$MAX_RETRIES"
    sleep 3
done

if [ $RETRY -ge $MAX_RETRIES ]; then
    echo "  WARNING: Could not run migrations — continuing in limited mode"
fi

# Generate demo data if not present
if [ ! -f "/app/data/demo/DEMO_METADATA.json" ]; then
    echo "  Generating demo data..."
    python -m data_pipeline.run_pipeline --demo-only --skip-training
fi

# Train models if not present
if [ ! -f "/app/models/rf_24h.pkl" ]; then
    echo "  Checking sea ice models..."
    if [ -f "/app/scripts/train_sea_ice.py" ]; then
        python /app/scripts/train_sea_ice.py || echo "  Model training skipped (using baselines)"
    else
        echo "  Model training skipped (using physics baseline)"
    fi
fi

echo "=== Starting POLAR-AI API server ==="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
