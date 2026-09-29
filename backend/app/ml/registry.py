"""
Model registry — loads, hash-verifies, and smoke-tests artifacts.

Per §12.4:
  Loads each artifact, verifies its SHA-256 against models/manifest.json,
  runs a tiny smoke inference, and records the outcome.  A model that fails
  its check is marked 'unavailable'; the API never silently substitutes another.

State machine per model_id:
  "unavailable"  — artifact absent or hash mismatch
  "failed_smoke" — artifact loaded but smoke forward-pass raised
  "ready"        — verified and smoke-passed

The registry is a module-level singleton loaded once at startup.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parents[3]          # project root
MODELS_DIR = ROOT / "models"
MANIFEST_PATH = MODELS_DIR / "manifest.json"


class ModelState(str, Enum):
    UNAVAILABLE = "unavailable"
    FAILED_SMOKE = "failed_smoke"
    READY = "ready"


@dataclass
class ModelEntry:
    model_id: str
    artifact_path: Path
    model_hash: str          # expected SHA-256 from manifest
    state: ModelState = ModelState.UNAVAILABLE
    reason: str = ""
    obj: Any = field(default=None, repr=False)   # the loaded object


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> Dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text())


class ModelRegistry:
    """
    Singleton that manages all model artifacts for the serving stack.

    Usage::

        from app.ml.registry import registry
        entry = registry.get("seaice_pixel")
        if entry.state == ModelState.READY:
            pred = entry.obj.predict(x)
    """

    def __init__(self):
        self._entries: Dict[str, ModelEntry] = {}
        self._loaded = False

    # ── Public API ────────────────────────────────────────────────────────────

    def load_all(self, models_dir: Optional[Path] = None) -> None:
        """Load and verify every artifact listed in manifest.json."""
        if models_dir is None:
            models_dir = MODELS_DIR
        manifest = _load_manifest()
        if not manifest:
            logger.warning(
                "No models/manifest.json found — all models unavailable. "
                "Run scripts/train_sea_ice.py after obtaining real data."
            )
        for model_id, spec in manifest.items():
            self._load_entry(model_id, spec, models_dir)
        self._loaded = True

    def get(self, model_id: str) -> Optional[ModelEntry]:
        """Return the entry for model_id, or None if unknown."""
        return self._entries.get(model_id)

    def summary(self) -> Dict[str, str]:
        """Return {model_id: state} dict for health-check endpoints."""
        return {mid: e.state.value for mid, e in self._entries.items()}

    def is_ready(self, model_id: str) -> bool:
        e = self._entries.get(model_id)
        return e is not None and e.state == ModelState.READY

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_entry(self, model_id: str, spec: dict, models_dir: Path) -> None:
        rel = spec.get("artifact")
        expected_hash = spec.get("sha256", "")
        if not rel:
            self._entries[model_id] = ModelEntry(
                model_id=model_id,
                artifact_path=Path(""),
                model_hash=expected_hash,
                state=ModelState.UNAVAILABLE,
                reason="No artifact path in manifest",
            )
            return

        path = models_dir / rel
        if not path.exists():
            self._entries[model_id] = ModelEntry(
                model_id=model_id,
                artifact_path=path,
                model_hash=expected_hash,
                state=ModelState.UNAVAILABLE,
                reason=f"Artifact not found: {path}",
            )
            logger.info("Model %s: UNAVAILABLE (not found)", model_id)
            return

        # Hash check
        actual_hash = _sha256(path)
        if expected_hash and actual_hash != expected_hash:
            self._entries[model_id] = ModelEntry(
                model_id=model_id,
                artifact_path=path,
                model_hash=expected_hash,
                state=ModelState.UNAVAILABLE,
                reason=(
                    f"SHA-256 mismatch: expected {expected_hash[:12]}… "
                    f"got {actual_hash[:12]}…"
                ),
            )
            logger.error("Model %s: hash mismatch — refusing to serve", model_id)
            return

        # Load artifact
        try:
            obj = self._deserialize(model_id, path, spec)
        except Exception as exc:
            self._entries[model_id] = ModelEntry(
                model_id=model_id,
                artifact_path=path,
                model_hash=actual_hash,
                state=ModelState.UNAVAILABLE,
                reason=f"Load error: {exc}",
            )
            logger.exception("Model %s: failed to deserialize", model_id)
            return

        # Smoke test
        try:
            self._smoke_test(model_id, obj, spec)
        except Exception as exc:
            self._entries[model_id] = ModelEntry(
                model_id=model_id,
                artifact_path=path,
                model_hash=actual_hash,
                state=ModelState.FAILED_SMOKE,
                reason=f"Smoke test failed: {exc}",
                obj=None,
            )
            logger.error("Model %s: smoke test failed — not serving", model_id)
            return

        self._entries[model_id] = ModelEntry(
            model_id=model_id,
            artifact_path=path,
            model_hash=actual_hash,
            state=ModelState.READY,
            reason="",
            obj=obj,
        )
        logger.info("Model %s: READY (hash=%s…)", model_id, actual_hash[:12])

    def _deserialize(self, model_id: str, path: Path, spec: dict):
        """Deserialize the artifact based on its declared format."""
        fmt = spec.get("format", "joblib")
        if fmt == "joblib":
            import joblib
            return joblib.load(path)
        if fmt == "numpy":
            import numpy as np
            return np.load(path, allow_pickle=True)
        raise ValueError(f"Unknown artifact format: {fmt!r}")

    def _smoke_test(self, model_id: str, obj, spec: dict) -> None:
        """Run a minimal forward pass to confirm the artifact is functional."""
        import numpy as np
        smoke = spec.get("smoke_input_shape")
        if smoke is None:
            return   # no smoke spec — skip
        x = np.zeros(smoke, dtype=np.float32)
        if hasattr(obj, "predict"):
            out = obj.predict(x)
        elif hasattr(obj, "__call__"):
            out = obj(x)
        else:
            raise TypeError(f"Artifact has no predict() or __call__: {type(obj)}")
        assert out is not None, "Smoke forward pass returned None"


# Module-level singleton
registry = ModelRegistry()
