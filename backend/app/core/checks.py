"""Shared, fail-closed validation checks for ingested datasets."""
from dataclasses import dataclass, field
from typing import Any
import numpy as np

@dataclass
class Finding:
    severity: str
    check: str
    message: str

@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)
    @property
    def errors(self): return [f for f in self.findings if f.severity == "error"]
    @property
    def ok(self): return not self.errors
    def error(self, check, message): self.findings.append(Finding("error", check, message))
    def warning(self, check, message): self.findings.append(Finding("warning", check, message))

def validate_units(ds: Any, variables: list[str], report: ValidationReport):
    for name in variables:
        if name in ds and not ds[name].attrs.get("units"):
            report.error("units", f"{name} has no declared units")

def validate_ranges(ds: Any, ranges: dict[str, tuple[float, float]], report: ValidationReport):
    for name, (lo, hi) in ranges.items():
        if name not in ds: continue
        values = np.asarray(ds[name].values)
        finite = values[np.isfinite(values)]
        if finite.size and (finite.min() < lo or finite.max() > hi):
            report.error("range", f"{name} outside [{lo}, {hi}]")

def validate_coordinates(ds: Any, report: ValidationReport):
    for name in ("lat", "latitude", "lon", "longitude"):
        if name in ds.coords:
            values = np.asarray(ds[name].values)
            if values.ndim == 1 and len(values) > 1 and np.any(np.diff(values) <= 0):
                report.error("coordinates", f"{name} is not strictly monotonic")

def validate_dataset(ds: Any, variables: list[str] = None, ranges: dict[str, tuple[float, float]] = None) -> ValidationReport:
    report = ValidationReport()
    variables = variables or list(ds.data_vars)
    validate_units(ds, variables, report)
    validate_ranges(ds, ranges or {}, report)
    validate_coordinates(ds, report)
    return report
