# Branding & Design System

Everything visual is driven by [src/theme/tokens.css](src/theme/tokens.css). Change a
token there and every page follows. Do not hard-code a colour, size, or radius
in a component.

---

## The three rules

**1. Blue is the brand. Red is a status.**

Red means *a deterministic rule fired — escalate now*. The moment red also
appears on a logo, a button, or a heading, the alert stops being an alert.

**2. Colour marks, it does not fill.**

Severity shows in a left rail, a numeral, and a small chip. **No card, row, or
tile ever fills with red.** A worklist of pink rows makes the alerting ones
invisible — the point is that the eye lands on the two that matter, not the
twelve that exist. The cohort is deliberately bottom-heavy for the same reason
(see `_STRATA` in [src/data.py](src/data.py)): roughly two alerting in twelve,
which is what a real waiting room looks like.

**3. Surfaces separate by tone, not by outline.**

There are no card borders anywhere. White sits on light grey; a soft shadow does
the rest. Nothing is a box inside a box inside a box.

| Colour | Means | Allowed on |
|---|---|---|
| Blue `#0169FF` | brand, structure, "stable" | rail, nav, primary buttons, links, focus |
| Grey `#8B9099` | routine, secondary text | labels, metadata, NEWS2 1–2 |
| Amber `#E39A2E` | **watch** — rising, not yet alerting | NEWS2 3–4, component scores 1–2 |
| Red `#C63032` | **escalate** — a rule fired | row rail, numeral, delta chip, alert block |

The score → colour mapping lives in exactly one place —
[src/severity.py](src/severity.py) — so it stays auditable.

---

## House style

- **No `·` and no `|`.** Ever. Facts get their own labelled field
  (`detail_grid`) or their own spaced span (`queue_row`'s `meta` list). This
  extends to data: the dataset joins complaints with pipes, and
  `data._humanise()` expands them to words before anything reaches the UI.
- **One number per tile.** Never two metrics in one card.
- **8pt spacing grid.** `--s-1` … `--s-9`. Card padding `--s-6`; block gutters `--s-5`.
- **Motion is a signal.** Only the escalate state animates, and it stops under
  `prefers-reduced-motion`.

---

## Themes

Light is primary; dark is a full counterpart for night shift, toggled from the
rail.

```
                    LIGHT              DARK
canvas              #EEEFF1            #0A0B0D
surface             #FFFFFF            #16181C
ink                 #0A0C10            #FFFFFF
ink-muted           #8B9099            #838A95
accent              #0169FF            #4A90FF   ← lifted
alert               #C63032            #F0555A   ← lifted
watch               #E39A2E            #F0B454   ← lifted
```

**Why accent and alert shift in dark:** `#0169FF` and `#C63032` both fall below
4.5:1 against a near-black canvas at body size. The lifted values pass. Never
reuse the light values on dark.

**How the switch works:** Streamlit strips `<script>` from injected markup, so we
cannot toggle a `data-theme` attribute at runtime. Instead
[src/theme/inject.py](src/theme/inject.py) promotes the active theme's block to
`:root` in Python before injecting. The dark block sits after the light block in
the file, so when promoted it wins on source order — no `!important`, no JS.

---

## Type

**Urbanist** (Google Fonts, 400/500/600/700), loaded via `@import`.

| Token | Size | Use |
|---|---|---|
| `--t-display` | 46px | the one headline per page |
| `--t-h1` | 34px | patient name |
| `--t-h2` | 24px | section titles, queue numerals |
| `--t-h3` | 19px | card titles, alert prose |
| `--t-body` | 17px | body copy |
| `--t-small` | 14px | metadata |
| `--t-label` | 11px | uppercase, `0.1em` tracking |
| `--t-metric` | 42px | the number in a stat tile |

All numerals use `font-variant-numeric: tabular-nums` so digits don't jitter
when a NEWS2 score updates.

---

## Layout

A **76px icon rail** (Streamlit's sidebar, restyled) holds everything
navigational: logo, the three views, night shift, and resample. Nothing
descriptive lives there — the rail is for controls only.

Views are rail destinations, not tabs: **Next action required**, **Reassessment
queue**, **Method**. Queue rows open a patient via the chevron on the right,
which sets `session_state.selected` and switches view.

---

## The anatomy figure

Not decoration — it is the NEWS2 audit trail rendered.
[src/ui/anatomy.py](src/ui/anatomy.py) fills each organ from its own component
subscore, so the figure cannot show anything the rules did not compute.

Body outline: **"Human silhouette gender neutral front.svg"** by Sebastian
Wallroth, Wikimedia Commons, **CC0 1.0** (public domain, no attribution
required — credited anyway). Stored in
[src/ui/body_asset.py](src/ui/body_asset.py); organ geometry is authored in the
same 148 × 318 coordinate space.

| Zone | Driven by | Worst-score-wins across |
|---|---|---|
| Head | consciousness | `consciousness` |
| Lungs | respiration | `resp`, `spo2`, `o2` |
| Heart | heart rate | `hr` |
| Vessels | systolic BP | `sbp` |
| **Outline** | temperature | `temp` |

Per-zone fill: 0 → near-invisible neutral, 1 → amber 30%, 2 → amber 62%,
3 → red 80% + pulse. **Zones stay invisible at score 0** so only what actually
scores draws the eye, and the readout below lists only non-zero zones.

**Temperature colours the outline, not the fill.** Washing the silhouette reads
as skin tone and drowns the organ zones — tried and rejected.

---

## Running it

```
streamlit run src/app.py     # from the repo root
```

Run it from the **root**, not from `src/`. Streamlit only reads
`.streamlit/config.toml` from the working directory, and that file resets
`primaryColor` from Streamlit's stock `#FF4B4B` to brand blue. Start it from
`src/` and every checkbox, form submit and spinner turns red — which in this
app means "a deterministic rule fired".

## Components

From [src/ui/components.py](src/ui/components.py). Every function returns an HTML
string; render with `st.markdown(..., unsafe_allow_html=True)`. All interpolated
text is escaped — **Gemma's output is never trusted as markup.**

```python
page_header(eyebrow, headline, sub)
section(title, sub)
patient_header(name, band_key, complaint)
detail_grid([(label, value), (label, value, "wide")])   # "wide" spans the row
metric_strip([(label, value, tone)])                    # compact secondary numbers
vitals_row([(label, value, is_abnormal)])
stat(label, value, foot, icon, tone)                    # tone colours the numeral only
pill(band_key, text); delta_chip(delta); ai_tag(text)
queue_row(rank, name, complaint, meta_list, news2, band_key, due, delta, selected)
alert_card(why, reasons, interval_note, fired)
figure(components)
```

### The agent brief

[src/agent.py](src/agent.py) is where Gemma does real work. It receives the
full picture — trajectory, per-parameter NEWS2 breakdown, comorbidities,
arrival mode, waiting time, which rules fired, and why the interval landed
where it did — and returns a structured brief: headline, what changed, what to
check first, how the history colours the reading, and why this window suits
this patient.

It is given the escalation decision and the interval as **settled facts** and
is forbidden from re-deriving or contradicting them. Malformed or incomplete
responses are rejected by `_validate()` and replaced with a deterministic
brief built only from the same facts, so the panel can never show invented
content.

### The alert card contract

Gemma's sentence sits on top; the rule that fired sits underneath in monospace,
**always visible and never collapsible**. A nurse must be able to see
*"alerted because the RR component hit 3"* without clicking. That receipt is
what makes the product defensible.

---

## Data

[src/data.py](src/data.py) builds the cohort from
`data/raw/triage_features_control.csv` — real ED visits. NEWS2 is computed by
[src/news2.py](src/news2.py) from raw vitals at **both** timepoints (`triage_*`
and `last_*`), never read from the dataset's precomputed columns, so the number
on screen always comes from our own engine. Triage → last is what produces the
delta that feeds the "rose by ≥ 2" rule.

Patients are identified by `PT-<source_row_id>`. The dataset has no names, and
inventing them would misrepresent real records.

---

## Extending to a new page

1. `inject_theme()` once, before anything renders.
2. Open with `page_header()` — one headline, stated large.
3. At most four `stat()` tiles in a row.
4. `section()`, then content.
5. Reach for an existing component. New ones use tokens only, and get documented here.

Never introduce a colour outside the ramp, never use red for anything but a
fired rule, and never fill a surface with a severity colour.

---

## The recheck clock

`DueAt` is always derived, never stored as a literal: it is `LastObsAt +
interval`, recomputed on every pass through `recalculate_and_sort_queue`. A
re-scored patient therefore cannot keep an interval the rules no longer
support. Recording a reassessment sets `LastObsAt` to now, which resets the
countdown.

`anchor_clock()` maps the dataset's recorded observation times onto the wall
clock. Staleness is expressed as a multiple of each patient's **own** interval
(oldest 1.4x, freshest 0.1x) rather than in flat minutes — the dataset spans a
whole day, so absolute spacing put patients hundreds of minutes past due, and
flat minutes tipped almost everyone overdue at once because most intervals here
are 15 to 30 minutes.

## Streamlit gotchas already handled

These cost real debugging time; don't reintroduce them.

- **Tabs** — Streamlit ≥1.55 uses react-aria (`[data-testid="stTab"]`), not
  BaseWeb. Both selectors are kept.
- **Buttons with `help=`** — get wrapped in a tooltip target, so `.stButton >
  button` misses them. Use the descendant selector.
- **A wrapper `<div>` from `st.markdown` does not contain the next widget.**
  Style widgets via Streamlit's `st-key-<key>` class instead
  (`[class*="st-key-open_"] button`).
- **Material icons** — a broad `font-family` override leaks ligature names like
  `keyboard_double_arrow_left` into the chrome. `tokens.css` re-asserts the icon font.
- **Headings** — Streamlit's own `h3` rule out-specifies a bare class, stranding
  sidebar headings on the light palette in dark mode.
- **`primaryColor` defaults to red.** See "Running it" above.
- **Form submits are `stFormSubmitButton`, not `stButton`**, so they miss the
  button rules and fall back to Streamlit's own theme.
- **`AppTest` does not put the script's directory on `sys.path`** the way
  `streamlit run` does, so `app.py` asserts it itself.
- **Editing `tokens.css` alone won't hot-reload** — the stylesheet is memoized
  and Streamlit only watches `.py`. Restart the server.
- **Wrapping a long SVG path across Python string literals drops the joining
  space** and fuses two coordinates into a third, wrong number — the figure
  renders as a smear. `body_asset.py` keeps a trailing space on every line and
  the generator asserts an exact round-trip.
