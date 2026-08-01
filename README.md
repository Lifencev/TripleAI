# Triage Re-Evaluation Monitor — TripleAI

A reassessment monitor for the emergency-department waiting room. It keeps a
risk-ranked worklist of patients who have been triaged but not yet seen, and
tells the nurse who to recheck next, when, and why.

Built for **Track 1: Clinical Triage**.

---

## The problem

Patients already triaged but not yet seen can quietly deteriorate in the
waiting room. Fixed reassessment timers exist — recheck a high-acuity patient
every X minutes — but they are constantly missed when the department is busy.
The patient nobody went back to is the one this catches.

## What it does

Instead of one fixed timer per patient, it maintains a **risk-ranked
reassessment queue**: a worklist ordered by rule severity, then by NEWS2.

1. **Score.** NEWS2 is computed from the recorded vitals at two timepoints —
   at triage, and at the latest observation.
2. **Set the interval.** `min(NEWS2-band interval, ESI acuity floor)` — the
   stricter of the two rulebooks wins, so neither can silently override the
   other.
3. **Run the clock.** Each patient carries a due time of
   `last observation + interval`. It counts down live and turns red when
   missed, reading *"Overdue by 6 minutes"* rather than rounding to zero.
4. **Evaluate.** An alert fires if **any** of:
   - NEWS2 aggregate reaches 5, or
   - any single parameter scores 3, or
   - NEWS2 rose by 2 or more since the last check.

   If NEWS2 dropped by 2 or more, the interval relaxes and the patient sinks
   in the queue.
5. **Brief.** Gemma turns the clinical picture into a reassessment brief the
   nurse can act on.

### Recording a reassessment

A nurse rechecks a patient, enters what they found (resp rate, SpO₂,
supplemental oxygen, systolic BP, pulse, temperature, consciousness), and the
whole pipeline re-derives from scratch: score, band, interval, due time and
queue position. The previous reading becomes the baseline the next delta is
measured against, so *"rose by 2 or more"* compares this recheck to the last
one. **No interval is hardcoded — every one is computed.**

---

## The design principle: rules decide, Gemma explains

This split is what makes the output defensible.

| | Decides | Never does |
|---|---|---|
| **Rules** | Who escalates, and when the next check is due | Never phrase or interpret |
| **Gemma** | The wording of the reassessment brief | Never sets acuity, interval or priority |

A nurse must always be able to see *"alerted because the respiratory rate
component hit 3"*. The rule that fired is printed under every brief, in
monospace, and is never collapsible.

### What the agent actually does

[`src/agent.py`](src/agent.py) receives the full picture — trajectory,
per-parameter NEWS2 breakdown, comorbidities, arrival mode, waiting time,
which rules fired, and why the interval landed where it did — and returns a
structured brief:

- **headline** — one line, read in five seconds
- **what changed** — the trajectory in clinical terms
- **check these first** — three or four specific assessments, most urgent first
- **history in context** — how the comorbidities change how you read the numbers
- **why this window** — why this interval suits this patient

Real output, for a 41-year-old with chronic kidney disease whose NEWS2 went
2 → 5:

> Chronic kidney disease increases the risk of fluid overload and metabolic
> instability, complicating the interpretation of tachypnoea.

That is inference the rules cannot produce. The escalation decision and the
interval are handed to the agent as **settled facts** it may not re-derive.
Malformed or incomplete responses are rejected and replaced with a brief built
from the same facts, so the panel can never show invented content.

---

## Data

`data/raw/triage_features_control.csv` — real ED visits. **Gitignored; copy it
in locally.** The app accepts it under `data/raw/` or `data/processed/`.

1,499 visits, 73 columns. 474 have a complete second set of vitals, which is
what makes a patient monitorable — without a later reading there is no
trajectory to watch.

Each row carries identity (`patient_id`, `stay_id`), timestamps
(`arrival_time`, `triage_time`, `measurement_time`), vitals at two timepoints
(`triage_*` and `last_*`), ESI level, arrival mode, chief complaints and
comorbidity history.

- **NEWS2 is always computed by our own engine** from the raw vitals, never
  read from the dataset's precomputed columns. The number on screen comes from
  [`src/news2.py`](src/news2.py).
- **Consciousness** is taken from the dataset's `alert` flag, derived from the
  altered-mental-status, confusion, lethargy and unresponsive complaint fields.
- **Cohort selection is stratified** so the worklist spans the acuity range,
  including a "rising" stratum drawn on the observed change rather than the
  absolute score. Without it the delta rule never fires in a sampled cohort,
  because visits that end high usually started high. Roughly three of twelve
  alert — a real waiting room is mostly fine, and if half the board is red then
  red means nothing.
- Patients are shown by their dataset `patient_id`. The data has no names and
  inventing them would misrepresent real records.

---

## Running it

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/streamlit run src/app.py
```

**Run from the repository root, not from `src/`.** Streamlit only reads
`.streamlit/config.toml` from the working directory, and that file resets
`primaryColor` from Streamlit's stock red to brand blue. Start it from `src/`
and every checkbox and form button turns red — the colour this app reserves
for a fired rule.

Gemma is reached through the Spur API. Copy `.env.example` to `.env` and set
`SPUR_GEMMA_4_KEY`. Without a key the app runs fine and shows a rule-derived
brief instead.

---

## The three views

- **Next action required** — one patient in full: the anatomy figure, the
  score trajectory with timestamps, live countdown, vitals, the reassessment
  form and the agent brief.
- **Reassessment queue** — the ranked worklist, with admit-next and a
  deterioration simulator for demos.
- **Method** — the loop, the three alert rules, and who is allowed to decide
  what.

### The anatomy figure

Not decoration. Each organ zone is filled from its own NEWS2 component
subscore, so the figure is the audit trail rendered: head from consciousness,
lungs from respiration, heart from heart rate, vessels from systolic BP, and
the body outline from temperature. If the lungs are red, `resp`/`spo2`/`o2`
scored 3.

---

## Layout

```
src/
  app.py            Streamlit shell and the three views
  news2.py          NEWS2 scoring
  time_interval.py  NEWS2 band intervals, ESI floor, stricter-wins combiner
  severity.py       the only place a score becomes a colour
  data.py           cohort loading from the real dataset
  agent.py          the Gemma reassessment brief
  theme/            design tokens, light and dark
  ui/               components and the anatomy figure
```

Design system and conventions are documented in [BRANDING.md](BRANDING.md).

## Not built yet

- `src/rag.py` — RAG over published reassessment-interval guidance, so the
  trigger could cite a guideline rather than our own ESI map.
- The validation analysis: the dataset carries `low_acuity_admitted_label`
  (230 positives) and `news2_delta_triage_to_worst`, which is everything
  needed to show the NEWS2 delta separates admitted-low-acuity from discharged
  patients. No code computes it yet.
- `src/prompts.py` and `src/ivan.py` are superseded and no longer imported;
  the agent's prompt lives in `src/agent.py`.
