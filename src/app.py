"""Triage Re-Evaluation Monitor.

Design system: src/theme (tokens) and src/ui (markup).
Deterministic engine: src/news2.py, src/time_interval.py, src/severity.py.
Cohort: real ED visits from data/raw/triage_features_control.csv (src/data.py).

Gemma is called for language only — it phrases an alert the rules already
raised. It never assigns a band, an interval, or a priority.
"""

import json
import os
import random

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from data import load_pool
from news2 import news2
from prompts import SYSTEM_PROMPT
from severity import band, relaxing
from theme import current_mode, inject_theme, toggle_mode
from time_interval import next_eval_interval
from ui import (
    alert_card,
    card,
    detail_grid,
    figure,
    flow_steps,
    icon,
    page_header,
    patient_header,
    queue_row,
    rule_list,
    score_trend,
    section,
    split_panel,
    stat,
    vitals_table,
)

load_dotenv()
SPUR_API_KEY = os.getenv("SPUR_GEMMA_4_KEY")
API_URL = "https://ai.spuric.com/v1/chat/completions"

st.set_page_config(
    page_title="Triage Re-Evaluation Monitor",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

MD = dict(unsafe_allow_html=True)

def _clock(ts) -> str:
    """Wall-clock time of a recorded observation, for provenance lines."""
    try:
        return pd.Timestamp(ts).strftime("%H:%M")
    except (ValueError, TypeError):
        return "unknown"


# NEWS2 thresholds per parameter, used only to flag a vital in the UI.
_ABNORMAL = {
    "RR":   lambda v: v <= 11 or v >= 21,
    "SpO2": lambda v: v <= 95,
    "SBP":  lambda v: v <= 110 or v >= 220,
    "HR":   lambda v: v <= 50 or v >= 91,
    "Temp": lambda v: v <= 36.0 or v >= 38.1,
}


# --- Deterministic pipeline -------------------------------------------------

def recalculate_and_sort_queue(df: pd.DataFrame) -> pd.DataFrame:
    """Applies the deterministic NEWS2 rules and orders the worklist."""
    if df.empty:
        return df

    scores, max_params, components, bands, intervals = [], [], [], [], []
    prev_scores = df["NEWS2_Prev"].tolist()

    for (_, row), prev in zip(df.iterrows(), prev_scores):
        result = news2(row["RR"], row["SpO2"], row["O2_supp"], row["SBP"],
                       row["HR"], row["Temp"], row["Alert"])
        delta = int(result["aggregate"] - prev)
        scores.append(result["aggregate"])
        max_params.append(result["max_single_param"])
        components.append(result["components"])
        bands.append(band(result["aggregate"], result["max_single_param"], delta))
        intervals.append(next_eval_interval(result["aggregate"],
                                            result["max_single_param"], int(row["ESI"])))

    df = df.assign(
        NEWS2_Score=scores, Max_Single_Param=max_params, Components=components,
        Band=bands, Interval=intervals,
        Delta=[int(s - p) for s, p in zip(scores, prev_scores)],
        _rank=[b["rank"] for b in bands],
    )
    return df.sort_values(["_rank", "NEWS2_Score"], ascending=False) \
             .drop(columns=["_rank"]).reset_index(drop=True)


OPENING_COHORT = 12


@st.cache_data(show_spinner="Loading patients from the triage dataset…")
def patient_pool() -> pd.DataFrame:
    """Every patient this session can show: the opening waiting room plus the
    intake queue that sequential admission draws from."""
    return load_pool()


def initial_queue() -> pd.DataFrame:
    return recalculate_and_sort_queue(patient_pool().head(OPENING_COHORT).copy())


def admit_next(queue: pd.DataFrame) -> pd.DataFrame | None:
    """Admit the next patient from intake and re-rank the worklist.

    Sequential arrival, ported from the intake flow on main: a patient walks
    in, is scored by the same deterministic pipeline, and lands wherever the
    rules put them — which may be straight to the top.
    """
    pool = patient_pool()
    already = set(queue["ID"]) if not queue.empty else set()
    remaining = pool[~pool["ID"].isin(already)]
    if remaining.empty:
        return None
    arriving = remaining.head(1)
    return recalculate_and_sort_queue(
        pd.concat([queue, arriving], ignore_index=True) if not queue.empty else arriving.copy()
    )


def generate_focus_note(patient: pd.Series) -> str:
    """Gemma API call using the structured JSON prompt.

    Language only. The band, the interval, and the decision to alert were all
    made by the deterministic rules before this function is ever called.
    """
    drivers = [{"param": k, "score": int(v)}
               for k, v in sorted(patient["Components"].items(), key=lambda kv: -kv[1]) if v > 0][:3]
    interval = patient["Interval"]

    payload_facts = {
        "patient": patient["ID"],
        "news2_prev": int(patient["NEWS2_Prev"]),
        "news2_now": int(patient["NEWS2_Score"]),
        "drivers": drivers or [{"param": "no scoring parameter", "score": 0}],
        "relevant_history": [patient["Complaint"], patient["History"]],
        "interval_status": (f"reassessment due every {interval['interval_min']} min, "
                            f"floored by {interval['driver']}"),
    }

    if not SPUR_API_KEY:
        names = ", ".join(d["param"] for d in drivers) or "no scoring parameter"
        return (f"Recheck {patient['ID']} now. NEWS2 {payload_facts['news2_prev']} to "
                f"{payload_facts['news2_now']}, driven by {names}. {patient['Complaint']}. "
                "(Offline fallback — set SPUR_GEMMA_4_KEY for Gemma prose.)")

    # prompts.py names the slot {JSON}. Substituting the wrong token fails
    # silently — Gemma would receive the literal placeholder and invent facts.
    prompt = SYSTEM_PROMPT.replace("{JSON}", json.dumps(payload_facts))
    try:
        r = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {SPUR_API_KEY}", "Content-Type": "application/json"},
            json={"model": "spur-gemma4", "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return (f"Recheck {patient['ID']} now. NEWS2 {payload_facts['news2_now']}. "
                f"(Gemma unavailable: {exc})")


# --- State ------------------------------------------------------------------

if "queue" not in st.session_state:
    st.session_state.queue = initial_queue()
if "view" not in st.session_state:
    st.session_state.view = "focus"
if "selected" not in st.session_state:
    st.session_state.selected = None
if "notes" not in st.session_state:
    st.session_state.notes = {}

inject_theme()


def _select(pid: str) -> None:
    st.session_state.selected = pid
    st.session_state.view = "focus"


# --- Icon rail --------------------------------------------------------------

with st.sidebar:
    st.markdown(f'<div class="rail-logo">{icon("stethoscope", 22)}</div>', **MD)

    if st.button("", icon=":material/monitor_heart:", help="Next action required",
                 key="nav_focus", width="stretch",
                 type="primary" if st.session_state.view == "focus" else "secondary"):
        st.session_state.view = "focus"
        st.rerun()

    if st.button("", icon=":material/format_list_bulleted:", help="Reassessment queue",
                 key="nav_queue", width="stretch",
                 type="primary" if st.session_state.view == "queue" else "secondary"):
        st.session_state.view = "queue"
        st.rerun()

    if st.button("", icon=":material/rule:", help="How the rules work",
                 key="nav_rules", width="stretch",
                 type="primary" if st.session_state.view == "rules" else "secondary"):
        st.session_state.view = "rules"
        st.rerun()

    st.markdown('<div class="rail-rule"></div>', **MD)

    dark = current_mode() == "dark"
    if st.button("", icon=":material/bedtime:" if not dark else ":material/light_mode:",
                 help="Night shift" if not dark else "Day shift",
                 key="nav_theme", width="stretch"):
        toggle_mode()
        st.rerun()

    if st.button("", icon=":material/refresh:", help="Resample cohort", key="nav_reset",
                 width="stretch"):
        patient_pool.clear()
        st.session_state.queue = initial_queue()
        st.session_state.selected = None
        st.session_state.notes = {}
        st.rerun()

q = st.session_state.queue
n_alerting = sum(1 for b in q["Band"] if b["key"] == "escalate") if not q.empty else 0
n_watch = sum(1 for b in q["Band"] if b["key"] == "watch") if not q.empty else 0
soonest = min((r["interval_min"] for r in q["Interval"]), default=0) if not q.empty else 0

# Selected patient defaults to the top of the worklist.
if not q.empty:
    if st.session_state.selected not in set(q["ID"]):
        st.session_state.selected = q.iloc[0]["ID"]
    patient = q[q["ID"] == st.session_state.selected].iloc[0]
else:
    patient = None


# --- View: next action required ---------------------------------------------

if st.session_state.view == "focus":
    if patient is None:
        st.markdown(page_header("Waiting room", "The waiting room is clear"), **MD)
    else:
        b, interval = patient["Band"], patient["Interval"]
        headline = ("Recheck this patient now" if b["key"] == "escalate"
                    else f"Next check in {interval['interval_min']} minutes")
        st.markdown(
            page_header(
                "Waiting room — triaged, not yet seen",
                headline,
                f"{n_alerting} of {len(q)} patients have a rule firing right now.",
            ),
            **MD,
        )

        left, right = st.columns([0.85, 1.5], gap="large")

        # The figure IS the audit trail: each zone is filled from its own
        # NEWS2 component subscore. Nothing here is model output.
        with left:
            st.markdown(figure(patient["Components"]), **MD)

        with right:
            st.markdown(patient_header(patient["ID"], b["key"], patient["Complaint"]), **MD)

            st.markdown(
                detail_grid([
                    ("Age", f"{patient['Age']} years"),
                    ("Sex", patient["Sex"]),
                    ("Acuity", f"ESI {patient['ESI']}"),
                    ("Arrived by", patient["Arrival"]),
                    ("Relevant history", patient["History"], "wide"),
                ]),
                **MD,
            )

            st.markdown(
                score_trend(
                    prev=int(patient["NEWS2_Prev"]),
                    now=int(patient["NEWS2_Score"]),
                    delta=int(patient["Delta"]),
                    prev_at=_clock(patient["TriagedAt"]),
                    now_at=_clock(patient["MeasuredAt"]),
                    gap_min=int(patient["ObsGapMin"]),
                    worst_param=int(patient["Max_Single_Param"]),
                    recheck=f"{interval['interval_min']} min",
                ),
                **MD,
            )

            st.markdown(
                vitals_table([
                    ("Resp", patient["RR"], _ABNORMAL["RR"](patient["RR"])),
                    ("SpO2", f"{patient['SpO2']}%", _ABNORMAL["SpO2"](patient["SpO2"])),
                    ("O2", "Yes" if patient["O2_supp"] else "No", bool(patient["O2_supp"])),
                    ("Systolic", patient["SBP"], _ABNORMAL["SBP"](patient["SBP"])),
                    ("Pulse", patient["HR"], _ABNORMAL["HR"](patient["HR"])),
                    ("Temp", f"{patient['Temp']}", _ABNORMAL["Temp"](patient["Temp"])),
                ]),
                **MD,
            )

            st.markdown('<div class="action-row"></div>', **MD)
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Generate focus note", type="primary", width="stretch"):
                    with st.spinner("Gemma is phrasing the alert…"):
                        st.session_state.notes[patient["ID"]] = generate_focus_note(patient)
            with c2:
                if st.button("Acknowledge", width="stretch"):
                    st.session_state.queue = q[q["ID"] != patient["ID"]].reset_index(drop=True)
                    st.session_state.selected = None
                    st.rerun()

            note = st.session_state.notes.get(patient["ID"])
            fired = bool(b["reasons"])
            st.markdown(
                alert_card(
                    note or ("Press Generate focus note — Gemma phrases the alert. "
                             "The rule below has already fired."
                             if fired else
                             "No reassessment rule has fired for this patient."),
                    b["reasons"] or ["no rule fired"],
                    (f"Interval floored by {interval['driver']}. NEWS2 band says "
                     f"{interval['news2_says']} minutes, ESI floor says "
                     f"{interval['esi_says']} minutes, and the stricter one wins."),
                    fired=fired,
                ),
                **MD,
            )


# --- View: reassessment queue -----------------------------------------------

elif st.session_state.view == "queue":
    st.markdown(
        page_header("Reassessment queue", "Who to recheck next",
                    "Ranked by rule severity, then by NEWS2."),
        **MD,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(stat("In waiting room", len(q), "triaged, not seen", "users"), **MD)
    with c2:
        st.markdown(stat("Alerting now", n_alerting, "rule fired", "alert",
                         tone="escalate" if n_alerting else None), **MD)
    with c3:
        st.markdown(stat("Rising", n_watch, "NEWS2 3 to 4", "pulse",
                         tone="watch" if n_watch else None), **MD)
    with c4:
        st.markdown(stat("Soonest recheck", f"{soonest}m", "across queue", "clock"), **MD)

    st.markdown(section("Worklist"), **MD)

    act_admit, act_sim, _ = st.columns([1, 1, 2])

    with act_admit:
        if st.button("Admit next patient", icon=":material/person_add:", width="stretch",
                     help="A new patient arrives from intake and is ranked by the rules."):
            updated = admit_next(q)
            if updated is None:
                st.toast("No patients left in intake.")
            else:
                st.session_state.queue = updated
                st.rerun()

    with act_sim:
        if st.button("Simulate deterioration", icon=":material/trending_down:", width="stretch",
                     help="Crashes the most stable patient's vitals to show the queue reorder."):
            if len(q) > 1:
                idx = len(q) - 1
                q.at[idx, "SpO2"] = random.randint(85, 89)
                q.at[idx, "RR"] = random.randint(25, 30)
                q.at[idx, "HR"] = random.randint(130, 145)
                st.session_state.queue = recalculate_and_sort_queue(q)
                st.rerun()

    for i, (_, row) in enumerate(q.iterrows(), 1):
        row_col, btn_col = st.columns([20, 1], vertical_alignment="center")
        with row_col:
            st.markdown(
                queue_row(
                    rank=i,
                    name=row["ID"],
                    complaint=row["Complaint"],
                    meta=[f"{row['Age']} years", row["Sex"], f"ESI {row['ESI']}", row["Arrival"]],
                    news2=int(row["NEWS2_Score"]),
                    band_key=row["Band"]["key"],
                    due=f"{row['Interval']['interval_min']} min",
                    delta=int(row["Delta"]),
                    selected=row["ID"] == st.session_state.selected,
                ),
                **MD,
            )
        with btn_col:
            if st.button("", icon=":material/chevron_right:", key=f"open_{row['ID']}",
                         help=f"Open {row['ID']}"):
                _select(row["ID"])
                st.rerun()

    if any(relaxing(d) for d in q["Delta"]):
        st.markdown(
            '<p class="t-small">Patients whose NEWS2 dropped by 2 or more have been '
            "de-prioritised and their interval relaxed.</p>",
            **MD,
        )


# --- View: method -----------------------------------------------------------

else:
    st.markdown(
        page_header("Method", "The rules decide, Gemma explains",
                    "An LLM never chooses who escalates."),
        **MD,
    )

    st.markdown(
        flow_steps([
            ("Triage", "Vitals recorded, NEWS2 scored, first interval set"),
            ("Wait", "Patient sits in the waiting room, not yet seen"),
            ("Re-score", "New vitals or the interval elapsing recomputes NEWS2"),
            ("Evaluate", "Three rules decide whether this becomes an alert"),
            ("Explain", "Gemma phrases why, in one line a nurse reads in seconds"),
        ]),
        **MD,
    )

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown(
            rule_list(
                "An alert fires if any of these is true",
                "Checked on every re-score. No weighting, no model, no discretion.",
                [
                    ("NEWS2 aggregate reaches 5",
                     "The standard escalation threshold for the combined score"),
                    ("Any single parameter scores 3",
                     "One severely abnormal vital escalates on its own, whatever the total"),
                    ("NEWS2 rose by 2 or more",
                     "Catches the patient still inside a safe band but moving the wrong way"),
                ],
            ),
            **MD,
        )
    with right:
        st.markdown(
            split_panel(
                "Who is allowed to decide what",
                "This split is the reason the output can be trusted.",
                [
                    ("Rules", "Who escalates, and when the next check is due",
                     "Never phrase or interpret"),
                    ("Gemma", "Wording of the focus note and the alert line",
                     "Never sets acuity, interval or priority"),
                ],
            ),
            **MD,
        )

    st.markdown(section("How the interval is chosen"), **MD)
    st.markdown(
        card(
            '<p class="t-body">Two rulebooks propose a reassessment interval, and the '
            "<b>stricter</b> one wins, so neither can silently override the other.</p>"
            '<div class="interval-demo">'
            '<div class="interval-demo__side"><span>NEWS2 band says</span><b>240 min</b></div>'
            '<div class="interval-demo__op">take the sooner</div>'
            '<div class="interval-demo__side"><span>ESI floor says</span><b>15 min</b></div>'
            '<div class="interval-demo__eq">&rarr;</div>'
            '<div class="interval-demo__out"><span>Recheck in</span><b>15 min</b></div>'
            "</div>",
            extra="panel",
        ),
        **MD,
    )
