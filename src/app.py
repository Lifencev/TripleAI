"""Triage Re-Evaluation Monitor.

Design system: src/theme (tokens) and src/ui (markup).
Deterministic engine: src/news2.py, src/time_interval.py, src/severity.py.
Cohort: real ED visits from data/raw/triage_features_control.csv (src/data.py).

Gemma (src/agent.py) writes the reassessment brief: what changed, what to
check first, and how the history colours the reading. It never decides who
escalates or how long the interval is — those come from the rules and are
handed to it as settled facts.
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# `streamlit run` puts the script's directory on sys.path, but importing this
# module any other way (AppTest, a REPL) does not, and the sibling imports
# below then fail. Assert it so the app runs from either directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import reassessment_brief  # noqa: E402
from data import load_pool  # noqa: E402
from news2 import news2  # noqa: E402
from severity import band, relaxing  # noqa: E402
from theme import current_mode, inject_theme, toggle_mode  # noqa: E402
from time_interval import next_eval_interval  # noqa: E402
from ui import (  # noqa: E402
    agent_brief,
    card,
    countdown,
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


def minutes_left(due_at) -> float:
    """Signed minutes to the recheck deadline. Negative means overdue."""
    return (pd.Timestamp(due_at) - pd.Timestamp(datetime.now())).total_seconds() / 60


def _due_label(due_at) -> str:
    """Queue-row deadline. Overdue is never rounded away to "0 min"."""
    left = minutes_left(due_at)
    return f"{int(abs(left))} min over" if left < 0 else f"{int(left)} min"


@st.fragment(run_every="20s")
def live_countdown(patient_id: str) -> None:
    """Ticks on its own so the deadline stays true without a page rerun.

    Reads the queue fresh each tick rather than closing over a row, so a
    reassessment recorded in between is reflected immediately.
    """
    queue = st.session_state.get("queue")
    if queue is None or queue.empty:
        return
    match = queue[queue["ID"] == patient_id]
    if match.empty:
        return
    row = match.iloc[0]
    st.markdown(
        countdown(minutes_left(row["DueAt"]), int(row["Interval"]["interval_min"])),
        unsafe_allow_html=True,
    )


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

    # The clock is derived, never stored as a literal: whenever the interval
    # changes the due time moves with it, so a re-scored patient cannot keep
    # an interval the rules no longer support.
    df["DueAt"] = [
        obs + timedelta(minutes=iv["interval_min"])
        for obs, iv in zip(df["LastObsAt"], df["Interval"])
    ]

    return df.sort_values(["_rank", "NEWS2_Score"], ascending=False) \
             .drop(columns=["_rank"]).reset_index(drop=True)


# How stale the oldest and freshest observations are, as a multiple of each
# patient's OWN reassessment interval. Above 1.0 is overdue.
CLOCK_STALEST = 1.4
CLOCK_FRESHEST = 0.1


def anchor_clock(df: pd.DataFrame) -> pd.DataFrame:
    """Map the dataset's recorded observation times onto the wall clock.

    The dataset spans a whole day. Preserving its absolute spacing put
    patients hundreds of minutes past due — true to the file, useless as a
    board. Preserving it as flat minutes instead made almost everyone overdue,
    because most intervals here are 15 to 30 minutes.

    So staleness is expressed relative to each patient's own interval: the
    oldest reading sits at 1.4x its interval (overdue), the freshest at 0.1x
    (just checked). Recorded order is preserved, roughly a third arrive
    overdue, and "overdue" means overdue against the rule that applies to
    that patient rather than an arbitrary clock.
    """
    df = df.copy()

    # Rank, not raw elapsed time: the recorded timestamps bunch up at the old
    # end, which tipped most of the board overdue at once. Ranking keeps the
    # recorded order but spreads staleness evenly across the cohort.
    n = len(df)
    if n <= 1:
        position = pd.Series(1.0, index=df.index, dtype=float)
    else:
        position = (df["MeasuredAt"].rank(method="first") - 1) / (n - 1)

    now = datetime.now()
    last_obs = []
    for pos, (_, row) in zip(position, df.iterrows()):
        interval = next_eval_interval(
            int(row["NEWS2_Score"]), int(row["Max_Single_Param"]), int(row["ESI"])
        )["interval_min"]
        staleness = CLOCK_STALEST - pos * (CLOCK_STALEST - CLOCK_FRESHEST)
        last_obs.append(now - timedelta(minutes=interval * staleness))

    df["LastObsAt"] = last_obs
    return df


OPENING_COHORT = 12


@st.cache_data(show_spinner="Loading patients from the triage dataset…")
def patient_pool() -> pd.DataFrame:
    """Every patient this session can show: the opening waiting room plus the
    intake queue that sequential admission draws from."""
    return load_pool()


def initial_queue() -> pd.DataFrame:
    return recalculate_and_sort_queue(
        anchor_clock(patient_pool().head(OPENING_COHORT).copy())
    )


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

    # A patient walking in now was observed at triage now, not hours ago.
    arriving = remaining.head(1).copy()
    arriving["LastObsAt"] = datetime.now()

    return recalculate_and_sort_queue(
        pd.concat([queue, arriving], ignore_index=True) if not queue.empty else arriving
    )


def record_observation(queue: pd.DataFrame, patient_id: str, vitals: dict) -> pd.DataFrame:
    """A nurse rechecked the patient. Store the new vitals as the latest
    reading, move the previous latest into the comparison slot, and let the
    pipeline re-derive score, band, interval and due time from scratch.
    """
    q = queue.copy()
    idx = q.index[q["ID"] == patient_id][0]

    # The previous latest becomes the baseline the next delta is measured
    # against, so "rose by 2 or more" compares this recheck to the last one.
    previous_obs = pd.Timestamp(q.at[idx, "LastObsAt"])
    q.at[idx, "NEWS2_Prev"] = int(q.at[idx, "NEWS2_Score"])
    q.at[idx, "TriagedAt"] = previous_obs

    now = datetime.now()
    q.at[idx, "MeasuredAt"] = now
    q.at[idx, "LastObsAt"] = now
    q.at[idx, "ObsGapMin"] = max(0, round((now - previous_obs).total_seconds() / 60))

    for column, value in vitals.items():
        q.at[idx, column] = value

    return recalculate_and_sort_queue(q)


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

            live_countdown(patient["ID"])

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

            # --- Reassessment: the nurse rechecks and enters what they found
            with st.expander("Record a reassessment", expanded=False):
                with st.form(f"vitals_{patient['ID']}", border=False):
                    v1, v2, v3 = st.columns(3)
                    with v1:
                        new_rr = st.number_input("Resp rate", 4, 60, int(patient["RR"]), 1)
                        new_sbp = st.number_input("Systolic BP", 50, 260, int(patient["SBP"]), 1)
                    with v2:
                        new_spo2 = st.number_input("SpO2 %", 50, 100, int(patient["SpO2"]), 1)
                        new_hr = st.number_input("Pulse", 20, 220, int(patient["HR"]), 1)
                    with v3:
                        new_temp = st.number_input("Temp C", 30.0, 43.0,
                                                   float(patient["Temp"]), 0.1, format="%.1f")
                        new_o2 = st.checkbox("On supplemental oxygen",
                                             value=bool(patient["O2_supp"]))
                    new_alert = st.checkbox("Alert and orientated", value=bool(patient["Alert"]))

                    if st.form_submit_button("Save and re-score", type="primary",
                                             width="stretch"):
                        st.session_state.queue = record_observation(
                            q, patient["ID"],
                            {"RR": int(new_rr), "SpO2": int(new_spo2),
                             "O2_supp": bool(new_o2), "SBP": int(new_sbp),
                             "HR": int(new_hr), "Temp": round(float(new_temp), 1),
                             "Alert": bool(new_alert)},
                        )
                        # The brief described the previous reading; it no longer holds.
                        st.session_state.notes.pop(patient["ID"], None)
                        st.rerun()

            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Generate reassessment brief", type="primary", width="stretch"):
                    with st.spinner("Gemma is reading the trajectory and history…"):
                        st.session_state.notes[patient["ID"]] = reassessment_brief(
                            patient, b, interval
                        )
            with c2:
                if st.button("Acknowledge", width="stretch"):
                    st.session_state.queue = q[q["ID"] != patient["ID"]].reset_index(drop=True)
                    st.session_state.selected = None
                    st.rerun()

            fired = bool(b["reasons"])
            brief = st.session_state.notes.get(patient["ID"])
            if brief is None:
                st.markdown(
                    card(
                        f'<div class="brief__top">'
                        f'{"" if not fired else ""}</div>'
                        '<p class="t-body">Press <b>Generate reassessment brief</b>. Gemma '
                        "reads the trajectory, the per-parameter breakdown, the comorbidities "
                        "and the arrival mode, then writes what to check first. The escalation "
                        "decision below was already made by the rules.</p>"
                        f'<div class="brief__rule" style="margin-top:16px">'
                        f'<span class="brief__rule-label">Escalation decided by</span>'
                        f'<span class="brief__codes">'
                        + "".join(f"<code>{r}</code>" for r in (b["reasons"] or ["no rule fired"]))
                        + "</span></div>"
                    ),
                    **MD,
                )
            else:
                st.markdown(agent_brief(brief, b["reasons"], fired), **MD)


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
                    due=_due_label(row["DueAt"]),
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
