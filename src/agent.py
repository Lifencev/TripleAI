"""The reassessment agent.

Gemma's job is synthesis, not arithmetic. The deterministic engine already
knows *that* a patient needs rechecking and *when*; what it cannot do is read
a 78-year-old's COPD history against a falling SpO2 and tell the nurse what to
put their hands on first.

So the agent is given the full clinical picture — trajectory, per-parameter
NEWS2 breakdown, comorbidities, arrival mode, how long the patient has waited,
which rules fired and why the interval landed where it did — and returns a
structured brief:

    headline           one line the nurse reads in five seconds
    why_now            what changed, in clinical terms
    focus_checks       the specific things to reassess first, in order
    history_note       how the comorbidities change the reading
    interval_rationale why this recheck window suits *this* patient

What the agent must never do is decide who escalates or move the interval.
Those come from src/severity.py and src/time_interval.py and are handed to the
agent as settled facts. If the model returns something malformed we fall back
to a deterministic brief rather than showing invented content.
"""

from __future__ import annotations

import json
import os
import re

import requests

API_URL = "https://ai.spuric.com/v1/chat/completions"
MODEL = "spur-gemma4"
TIMEOUT_S = 45

FIELDS = ("headline", "why_now", "focus_checks", "history_note", "interval_rationale")

# Parameter keys as NEWS2 reports them, in words a nurse would use.
_PARAM_NAMES = {
    "resp": "respiratory rate",
    "spo2": "oxygen saturation",
    "o2": "supplemental oxygen",
    "sbp": "systolic blood pressure",
    "hr": "heart rate",
    "temp": "temperature",
    "consciousness": "consciousness",
}

SYSTEM = """You are a reassessment agent supporting an emergency-department nurse.

A deterministic NEWS2 engine has ALREADY decided whether this patient is
escalating and when the next check is due. Those decisions are final and are
given to you as facts. Your job is to turn the clinical picture into a brief
the nurse can act on.

HARD RULES
- Never contradict, re-derive or second-guess the supplied scores, the rules
  that fired, or the reassessment interval. Do not propose a different
  interval or a different acuity.
- Never invent a number, symptom, medication or history item that is not in
  the input. If something is not given, do not mention it.
- Never state a diagnosis as fact and never recommend a treatment or drug.
  You may say what to assess, not what to give.
- British clinical English. No hedging ("perhaps", "might want to").
- Address the nurse directly and plainly.

Return ONLY a JSON object, no markdown fence, with exactly these keys:

{
  "headline": "one sentence under 22 words stating who to recheck and the single most important reason",
  "why_now": "2-3 sentences on what changed between the two readings and what that pattern suggests physiologically",
  "focus_checks": ["3-4 specific assessments, most urgent first, each under 12 words"],
  "history_note": "1-2 sentences on how this patient's history or arrival mode changes how you read these numbers. If there is no relevant history, say what is reassuring about its absence.",
  "interval_rationale": "1 sentence on why this recheck window is appropriate for this patient, consistent with the interval given"
}
"""


def build_facts(patient, band: dict, interval: dict) -> dict:
    """Assemble everything the agent is allowed to reason over.

    Deliberately explicit: the agent sees only this dict, so anything absent
    here cannot appear in the brief.
    """
    components = patient["Components"]
    drivers = [
        {"parameter": _PARAM_NAMES.get(k, k), "score": int(v)}
        for k, v in sorted(components.items(), key=lambda kv: -kv[1])
        if v > 0
    ]

    return {
        "patient": str(patient["ID"]),
        "age": int(patient["Age"]),
        "sex": str(patient["Sex"]),
        "chief_complaint": str(patient["Complaint"]),
        "history": str(patient["History"]),
        "arrival_mode": str(patient["Arrival"]),
        "esi_level": int(patient["ESI"]),
        "minutes_waiting": int(patient["WaitMin"]),
        "news2_at_triage": int(patient["NEWS2_Prev"]),
        "news2_latest": int(patient["NEWS2_Score"]),
        "news2_change": int(patient["Delta"]),
        "minutes_between_readings": int(patient["ObsGapMin"]),
        "worst_single_parameter": int(patient["Max_Single_Param"]),
        "driving_parameters": drivers,
        "latest_vitals": {
            "respiratory_rate": int(patient["RR"]),
            "oxygen_saturation": int(patient["SpO2"]),
            "on_supplemental_oxygen": bool(patient["O2_supp"]),
            "systolic_bp": int(patient["SBP"]),
            "heart_rate": int(patient["HR"]),
            "temperature_c": float(patient["Temp"]),
            "alert": bool(patient["Alert"]),
        },
        "severity_band": band["label"],
        "rules_that_fired": band["reasons"] or ["none"],
        "interval_minutes": int(interval["interval_min"]),
        "interval_driver": str(interval["driver"]),
        "news2_band_suggests_minutes": int(interval["news2_says"]),
        "esi_floor_suggests_minutes": int(interval["esi_says"]),
    }


def _fallback(facts: dict) -> dict:
    """Deterministic brief, used when Gemma is unavailable or misbehaves.

    Reads only from `facts`, so it can never introduce anything the rules did
    not already establish.
    """
    names = [d["parameter"] for d in facts["driving_parameters"]]
    change = facts["news2_change"]
    direction = "rose" if change > 0 else "fell" if change < 0 else "held"

    checks = [f"Repeat {n}" for n in names[:3]] or ["Repeat full observations"]
    checks.append("Confirm level of consciousness")

    return {
        "headline": (
            f"Recheck {facts['patient']} within {facts['interval_minutes']} minutes. "
            f"NEWS2 {facts['news2_at_triage']} to {facts['news2_latest']}."
        ),
        "why_now": (
            f"NEWS2 {direction} from {facts['news2_at_triage']} to {facts['news2_latest']} "
            f"over {facts['minutes_between_readings']} minutes, driven by "
            f"{', '.join(names) if names else 'no scoring parameter'}. "
            f"Highest single parameter score is {facts['worst_single_parameter']}."
        ),
        "focus_checks": checks,
        "history_note": (
            f"Recorded history: {facts['history']}. "
            f"Arrived by {facts['arrival_mode'].lower()} and has waited "
            f"{facts['minutes_waiting']} minutes."
        ),
        "interval_rationale": (
            f"The {facts['interval_minutes']} minute window is set by "
            f"{facts['interval_driver']}, the stricter of the two rulebooks."
        ),
        "_source": "fallback",
    }


def _extract_json(text: str) -> dict | None:
    """Models wrap JSON in prose or code fences more often than not."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.S)
        if brace:
            text = brace.group(0)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _validate(brief: dict) -> dict | None:
    """Every field present and non-empty, or we do not trust the response."""
    out: dict = {}
    for key in FIELDS:
        value = brief.get(key)
        if key == "focus_checks":
            if not isinstance(value, list):
                return None
            checks = [str(v).strip() for v in value if str(v).strip()]
            if not checks:
                return None
            out[key] = checks[:4]
        else:
            if not isinstance(value, str) or not value.strip():
                return None
            out[key] = value.strip()
    out["_source"] = "gemma"
    return out


def reassessment_brief(patient, band: dict, interval: dict,
                       api_key: str | None = None) -> dict:
    """Generate the brief. Always returns a usable dict."""
    facts = build_facts(patient, band, interval)
    key = api_key if api_key is not None else os.getenv("SPUR_GEMMA_4_KEY")

    if not key:
        brief = _fallback(facts)
        brief["_note"] = "Gemma offline. Set SPUR_GEMMA_4_KEY for the generated brief."
        return brief

    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": json.dumps(facts, indent=2)},
                ],
            },
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        brief = _fallback(facts)
        brief["_note"] = (
            f"Gemma unavailable ({type(exc).__name__}). Showing the rule-derived brief."
        )
        return brief

    validated = _validate(_extract_json(content) or {})
    if validated is None:
        brief = _fallback(facts)
        brief["_note"] = "Gemma returned an unusable response. Showing the rule-derived brief."
        return brief
    return validated
