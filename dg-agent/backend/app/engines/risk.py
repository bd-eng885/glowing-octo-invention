"""Configurable risk matrices (no single universal methodology is assumed)."""
from __future__ import annotations

DEFAULT_MATRIX = {
    "name": "Default 5x5 (example — configure to your organisation's methodology)",
    "likelihood": ["Rare", "Unlikely", "Possible", "Likely", "Almost certain"],
    "severity": ["Insignificant", "Minor", "Moderate", "Major", "Catastrophic"],
    "method": "product",  # score = likelihood_index * severity_index (1-based)
    "bands": [
        {"min": 1, "max": 4, "label": "Low", "color": "#2e7d32", "action": "Manage by routine procedures"},
        {"min": 5, "max": 9, "label": "Medium", "color": "#f9a825", "action": "Additional controls; supervisor review"},
        {"min": 10, "max": 16, "label": "High", "color": "#ef6c00", "action": "Senior management attention; controls before work"},
        {"min": 17, "max": 25, "label": "Extreme", "color": "#c62828", "action": "Stop / do not proceed until risk reduced"},
    ],
}


def validate_matrix(cfg: dict) -> list[str]:
    errs = []
    L, S = cfg.get("likelihood") or [], cfg.get("severity") or []
    if len(L) < 2 or len(S) < 2:
        errs.append("Matrix needs at least 2 likelihood and 2 severity levels.")
    bands = sorted(cfg.get("bands") or [], key=lambda b: b["min"])
    top = len(L) * len(S) if cfg.get("method", "product") == "product" else len(L) + len(S)
    expect = 1 if cfg.get("method", "product") == "product" else 2
    for b in bands:
        if b["min"] != expect:
            errs.append(f"Bands must be contiguous: expected band starting at {expect}, got {b['min']}.")
        expect = b["max"] + 1
    if bands and bands[-1]["max"] < top:
        errs.append(f"Bands do not cover maximum score {top}.")
    return errs


def rate(cfg: dict, likelihood: int, severity: int) -> dict:
    """likelihood/severity are 1-based indices into the configured scales."""
    L, S = cfg["likelihood"], cfg["severity"]
    if not (1 <= likelihood <= len(L) and 1 <= severity <= len(S)):
        raise ValueError("likelihood/severity out of range for this matrix")
    score = likelihood * severity if cfg.get("method", "product") == "product" else likelihood + severity
    band = next((b for b in cfg["bands"] if b["min"] <= score <= b["max"]), None)
    return {"likelihood": L[likelihood - 1], "severity": S[severity - 1], "score": score,
            "band": band["label"] if band else "UNRATED", "color": band.get("color") if band else None,
            "action": band.get("action") if band else "Band not configured"}


def assess_rows(cfg: dict, rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        row = dict(r)
        try:
            row["initial_rating"] = rate(cfg, int(r["likelihood"]), int(r["severity"]))
        except (KeyError, ValueError, TypeError):
            row["initial_rating"] = {"band": "UNRATED", "action": "Likelihood/severity missing or invalid"}
        if r.get("residual_likelihood") and r.get("residual_severity"):
            try:
                row["residual_rating"] = rate(cfg, int(r["residual_likelihood"]), int(r["residual_severity"]))
            except (ValueError, TypeError):
                row["residual_rating"] = {"band": "UNRATED"}
        out.append(row)
    return out
