"""Maps deterministic NEWS2 output onto the visual severity ramp.

This module is presentation logic, but it is the ONLY place a colour is
chosen from a score — so the mapping stays auditable in one file. It reads
the rules from the README and nothing else; no model output reaches here.

Ramp:  stable (blue) -> routine (grey) -> watch (amber) -> escalate (red)
Red appears if and only if one of the three alert rules fired.
"""

from typing import Iterable

# Ordered least to most severe. `var` is the CSS custom property in tokens.css.
BANDS = {
    "stable":   {"label": "Stable",   "var": "--sev-stable",   "rank": 0},
    "routine":  {"label": "Routine",  "var": "--sev-routine",  "rank": 1},
    "watch":    {"label": "Watch",    "var": "--sev-watch",    "rank": 2},
    "escalate": {"label": "Escalate", "var": "--sev-escalate", "rank": 3},
}

# NEWS2 component key -> (organ zone in the figure, human-readable source)
COMPONENT_ZONES = {
    "consciousness": ("head",     "Consciousness"),
    "resp":          ("lungs",    "Respiratory rate"),
    "spo2":          ("lungs",    "Oxygen saturation"),
    "o2":            ("lungs",    "Supplemental O₂"),
    "hr":            ("heart",    "Heart rate"),
    "sbp":           ("vessels",  "Systolic BP"),
    "temp":          ("body",     "Temperature"),
}

ZONE_ORDER = ("head", "lungs", "heart", "vessels", "body")
ZONE_LABELS = {
    "head":    "Head",
    "lungs":   "Lungs",
    "heart":   "Heart",
    "vessels": "Vessels",
    "body":    "Whole body",
}


def alert_reasons(aggregate: int, max_single_param: int, delta: int | None = None) -> list[str]:
    """The deterministic receipt: which rule(s) fired, in the README's wording.

    An empty list means no rule fired, so nothing may be shown in red.
    """
    reasons: list[str] = []
    if aggregate >= 5:
        reasons.append(f"NEWS2 aggregate {aggregate} ≥ 5")
    if max_single_param == 3:
        reasons.append("single parameter scored 3")
    if delta is not None and delta >= 2:
        reasons.append(f"NEWS2 rose by {delta} since last check")
    return reasons


def band(aggregate: int, max_single_param: int, delta: int | None = None) -> dict:
    """Classify a patient into one severity band.

    Returns the band key, its label, the CSS var, and the firing rules.
    """
    reasons = alert_reasons(aggregate, max_single_param, delta)
    if reasons:
        key = "escalate"
    elif aggregate >= 3:
        key = "watch"
    elif aggregate >= 1:
        key = "routine"
    else:
        key = "stable"

    return {"key": key, "reasons": reasons, **BANDS[key]}


def relaxing(delta: int | None) -> bool:
    """NEWS2 dropped by >= 2: relax the interval, de-prioritise in the queue."""
    return delta is not None and delta <= -2


def zone_levels(components: dict[str, int]) -> dict[str, dict]:
    """Fold NEWS2 components onto figure zones, worst-score-wins per zone.

    `components` is the dict returned by news2.news2()["components"].
    Each zone reports its driving score and which parameter produced it.
    """
    zones = {z: {"score": 0, "source": None} for z in ZONE_ORDER}

    for comp, score in components.items():
        mapping = COMPONENT_ZONES.get(comp)
        if mapping is None:
            continue
        zone, source = mapping
        if score > zones[zone]["score"] or zones[zone]["source"] is None:
            zones[zone] = {"score": score, "source": source}

    for zone in zones.values():
        zone["level"] = _zone_level(zone["score"])
    return zones


def _zone_level(score: int) -> str:
    """Per-parameter score (0-3) -> ramp step for that organ."""
    if score >= 3:
        return "escalate"
    if score >= 1:
        return "watch"
    return "idle"


def worst(bands: Iterable[dict]) -> dict | None:
    """Highest band in a collection — used for department-level summaries."""
    ordered = sorted(bands, key=lambda b: b["rank"], reverse=True)
    return ordered[0] if ordered else None
