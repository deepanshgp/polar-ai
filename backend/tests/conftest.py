"""
Pytest configuration — sets env vars so tests work without external APIs.
Tests run in DATA_MODE=demo to use deterministic synthetic data.
Production runs in DATA_MODE=live (see .env).
"""
import os
import pytest

# Tests always run in DEMO mode for deterministic, credential-free results
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_polar_ai.db")
os.environ["DATA_MODE"] = "demo"       # ← explicitly force DEMO for tests
os.environ.setdefault("DEMO_RANDOM_SEED", "42")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("UPDATE_INTERVAL_MINUTES", "60")
os.environ.setdefault("SCHEDULER_ENABLED", "false")

try:
    from app.config import settings
    settings.DATA_MODE = "demo"
except Exception:
    pass
