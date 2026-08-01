# Triage Re-Evaluation Monitor — Project by TripleAI
 
## The problem
Patients already triaged but not yet seen can quietly deteriorate in the waiting room. Fixed reassessment timers (recheck a high-acuity patient every X min) exist but are constantly missed when the ED is busy. We're building a system that catches these under-triaged, decompensating patients before a human would circle back to them.
 
## What we're building
A **triage re-evaluation co-pilot**. Instead of one fixed timer per patient, it maintains a **risk-ranked reassessment queue** — a worklist telling the nurse who to recheck next, in what order, and why. Population we're targeting: the **waiting room** (triaged, not yet seen).
 
## How it works (the loop)
1. **Intake** — patient arrives, we compute their NEWS2 score and initial acuity, then set the first re-eval interval. Gemma writes a short "focus note" for the nurse, grounded in whichever vitals are already abnormal.
2. **Interval** = `min(NEWS2-band interval, ESI acuity floor)` — we take the stricter (sooner) of the two rulebooks so neither can silently override the other.
3. **Recompute** — fires on *either* a timer tick (interval elapsed) *or* new vitals being entered. The timer trigger is what makes this a **monitor**, not a calculator — it catches the patient nobody went back to.
4. **Evaluate** — alert the nurse if **any** of:
   - NEWS2 aggregate ≥ 5, OR
   - any single parameter scores 3, OR
   - NEWS2 rose by ≥ 2 since last check.
   If NEWS2 *dropped* by ≥ 2, relax the interval and de-prioritize in the queue. Otherwise, reschedule at the new interval.
5. **Alert** — when triggered, Gemma explains *why* in one line a nurse can read in 5 seconds (e.g. "NEWS2 4→7, driven by RR 22→30 and new O₂ need; COPD with prior exacerbation — high decompensation risk").
## The key design principle: deterministic vs. Gemma
This split is the thing that makes the project trustworthy — state it clearly to anyone who asks.
- **Deterministic (the rules):** NEWS2 computation, the trigger decision, the interval lookup. A nurse must always be able to see *"alerted because the RR component hit 3."* An LLM never decides who escalates.
- **Gemma (language only):** the intake focus-note and the alert explanation. It explains and contextualizes a decision the rules already made — it does not make the call.
This pre-empts the most dangerous question: *"would you trust an LLM to decide who's dying?"* Our answer: we don't; it only explains.
 
## Data
Our dataset is **one row per visit** with `_min/_max/_median/_last` aggregates — it is **not a true time series**. We cannot literally replay a patient's trajectory from it. Two consequences:
- **For the live demo:** we simulate a plausible vital-sign stream per patient. Labeled clearly as synthetic — it's for showing the UI, not for evidence.
- **For real evaluation (no simulation needed):** we use a proxy label. Patients **admitted despite low initial acuity (ESI 3/4/5)** are our "missed deterioration" positives. We show that the NEWS2 delta (triage → worst aggregate) is systematically larger in that group than in discharged patients. That's a real, quantitative result from the cross-sectional data. **This is our validation slide.**
## Known approximations (name them, don't hide them)
- **Consciousness component** of NEWS2: dataset has no ACVPU field. We proxy it from `cc_alteredmentalstatus / cc_confusion / cc_lethargy / cc_unresponsive`. Under-detects subtle confusion.
- **ESI intervals:** unlike CTAS, ESI publishes **no** official reassessment intervals. Our ESI→interval map is a reasonable acuity-ordered approximation we impose, strongest for levels 1–3.
- **NEWS2 Scale 2** (chronic hypercapnic / some COPD patients): no flag in the data to identify them, so we use Scale 1 for everyone and note the limitation.
## MVP scope
- NEWS2 from the vital columns (with the consciousness proxy).
- The evaluation result: NEWS2-delta separates admitted-low-acuity from discharged. One chart, one number.
- Gemma alert generator: record + NEWS2 trajectory + history → the notification sentence.
- Minimal ranked-queue UI (Streamlit panel), alerts highlighted, patient queue.
- RAG over the CTAS reassessment-interval rules so the trigger cites a guideline instead of a hard-coded number.
## Stretch
- Trend detection over the last *k* readings.
