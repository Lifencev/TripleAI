"""Reusable markup for the design system.

Every function returns an HTML string; render with
`st.markdown(..., unsafe_allow_html=True)`. All interpolated text is escaped —
alert prose comes from Gemma and must never be trusted as markup.

House style: no middot or pipe separators anywhere. Facts get their own
labelled field so the eye can land on one thing at a time.
"""

from html import escape

from severity import BANDS

# --- Icons. Stroke-based, 24px grid, inherit currentColor. -----------------

_ICONS = {
    "users":    '<path d="M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 7a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7M22 20v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    "clock":    '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "pulse":    '<path d="M2 12h4l3 8 6-16 3 8h4"/>',
    "alert":    '<path d="M12 3 2.5 20h19L12 3zM12 10v4M12 17.5v.01"/>',
    "spark":    '<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4L12 3z"/>',
    "moon":     '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    "sun":      '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>',
    "layers":   '<path d="M12 3 3 8l9 5 9-5-9-5zM3 14l9 5 9-5"/>',
    "list":     '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    "chevron":  '<path d="M9 5l7 7-7 7"/>',
    "stethoscope": '<path d="M6 3v6a5 5 0 0 0 10 0V3M4.5 3h3M14.5 3h3M11 14v2a5 5 0 0 0 9 3M20 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"/>',
    "shield":   '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/>',
    "arrival":  '<path d="M3 20h18M6 20V9l6-4 6 4v11M10 20v-5h4v5"/>',
}


def icon(name: str, size: int = 20) -> str:
    body = _ICONS.get(name, _ICONS["pulse"])
    return (
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


# --- Page furniture ---------------------------------------------------------

def page_header(eyebrow: str, headline: str, sub: str | None = None) -> str:
    """The big, airy greeting block. One idea, stated large."""
    tail = f'<p class="t-body page-header__sub">{escape(sub)}</p>' if sub else ""
    return (
        f'<header class="page-header">'
        f'<p class="t-eyebrow">{escape(eyebrow)}</p>'
        f'<h1 class="t-display">{escape(headline)}</h1>{tail}</header>'
    )


def section(title: str, sub: str | None = None) -> str:
    tail = f'<p class="t-small section__sub">{escape(sub)}</p>' if sub else ""
    return f'<div class="section"><h2 class="t-h2">{escape(title)}</h2>{tail}</div>'


# --- Atoms ------------------------------------------------------------------

def pill(band_key: str, text: str | None = None) -> str:
    meta = BANDS.get(band_key, BANDS["routine"])
    return f'<span class="pill pill--{band_key}">{escape(text or meta["label"])}</span>'


def delta_chip(delta: int | None) -> str:
    """Renders the NEWS2 trend. +2 or worse is an alert rule in its own right."""
    if delta is None:
        return '<span class="delta">New</span>'
    if delta >= 2:
        return f'<span class="delta delta--up">&#9650; {delta:+d}</span>'
    if delta <= -2:
        return f'<span class="delta delta--down">&#9660; {delta:+d}</span>'
    if delta == 0:
        return '<span class="delta">No change</span>'
    return f'<span class="delta">{delta:+d}</span>'


def ai_tag(text: str = "Written by Gemma") -> str:
    return f'<span class="ai-tag">{icon("spark", 12)}{escape(text)}</span>'


# --- Stat tile --------------------------------------------------------------

def stat(label: str, value: str | int, foot: str = "", icon_name: str = "pulse",
         tone: str | None = None) -> str:
    """One number, one label. Never two metrics in one tile.

    `tone` colours the numeral only — the tile itself never fills with red.
    """
    mod = f" stat--{tone}" if tone in ("watch", "escalate") else ""
    foot_html = f'<div class="stat__foot">{escape(foot)}</div>' if foot else ""
    return (
        f'<div class="stat{mod}">'
        f'<div class="stat__head">'
        f'<span class="stat__icon">{icon(icon_name, 18)}</span>'
        f'<span class="stat__label">{escape(label)}</span></div>'
        f'<div class="stat__value">{escape(str(value))}</div>'
        f"{foot_html}</div>"
    )


def metric_strip(items: list[tuple[str, str, str | None]]) -> str:
    """Compact inline metrics: (label, value, tone). For secondary numbers
    that matter but must not dominate the page."""
    cells = "".join(
        f'<div class="metric{f" metric--{tone}" if tone in ("watch", "escalate") else ""}">'
        f'<span class="metric__label">{escape(label)}</span>'
        f'<span class="metric__value">{escape(str(value))}</span></div>'
        for label, value, tone in items
    )
    return f'<div class="metric-strip">{cells}</div>'


def detail_grid(items: list[tuple]) -> str:
    """Labelled facts, one per cell. Replaces middot-joined metadata runs.

    Items are (label, value) or (label, value, "wide") — wide spans the full
    row, for free text like a history list that would otherwise be squeezed
    into a narrow column.
    """
    cells = []
    for item in items:
        label, value = item[0], item[1]
        wide = " detail--wide" if len(item) > 2 and item[2] == "wide" else ""
        cells.append(
            f'<div class="detail{wide}"><span class="detail__label">{escape(label)}</span>'
            f'<span class="detail__value">{escape(str(value))}</span></div>'
        )
    return f'<div class="detail-grid">{"".join(cells)}</div>'


def vitals_table(items: list[tuple[str, str, bool]]) -> str:
    """(label, value, is_abnormal) as one compact table, not six boxes.

    Six padded tiles for six numbers is more chrome than content. A single
    table reads in one pass; abnormal values take colour and weight rather
    than a container of their own.
    """
    heads = "".join(f"<th>{escape(label)}</th>" for label, _, _ in items)
    cells = "".join(
        f'<td class="{"vt--flag" if flag else ""}">{escape(str(value))}</td>'
        for _, value, flag in items
    )
    return (
        f'<table class="vt"><thead><tr>{heads}</tr></thead>'
        f"<tbody><tr>{cells}</tr></tbody></table>"
    )


def score_trend(prev: int, now: int, delta: int | None,
                prev_at: str, now_at: str, gap_min: int,
                worst_param: int, recheck: str) -> str:
    """The two NEWS2 readings, with where each came from.

    "Now" is the latest recorded observation, not a live number — saying when
    each reading was taken is the difference between a trustworthy panel and
    an implied real-time feed that does not exist.
    """
    tone = ""
    if delta is not None and delta >= 2:
        tone = " score-trend--up"
    elif delta is not None and delta <= -2:
        tone = " score-trend--down"

    return (
        f'<div class="score-trend{tone}">'
        f'<div class="score-trend__main">'
        f'<div class="score-trend__pair">'
        f'<span class="score-trend__from">{prev}</span>'
        f'<span class="score-trend__arrow">&rarr;</span>'
        f'<span class="score-trend__to">{now}</span>'
        f"</div>"
        f'<div class="score-trend__meta">'
        f'<span class="score-trend__cap">NEWS2 at triage then latest reading</span>'
        f'<span class="score-trend__times">{escape(prev_at)} then {escape(now_at)}'
        f", {gap_min} minutes apart</span>"
        f"</div>{delta_chip(delta)}</div>"
        f'<div class="score-trend__side">'
        f'<div class="score-trend__stat"><span>Worst parameter</span>'
        f'<b class="{"is-max" if worst_param == 3 else ""}">{worst_param}</b></div>'
        f'<div class="score-trend__stat"><span>Recheck in</span><b>{escape(recheck)}</b></div>'
        f"</div></div>"
    )


# --- Patient header ---------------------------------------------------------

def patient_header(name: str, band_key: str, complaint: str) -> str:
    return (
        f'<div class="patient-head">'
        f'<div class="patient-head__top">'
        f'<h2 class="t-h1 patient-head__name">{escape(name)}</h2>'
        f"{pill(band_key)}</div>"
        f'<p class="t-body patient-head__cc">{escape(complaint)}</p></div>'
    )


# --- Queue ------------------------------------------------------------------

def queue_row(rank: int, name: str, complaint: str, meta: list[str], news2: int,
              band_key: str, due: str, delta: int | None = None,
              selected: bool = False) -> str:
    """One line of the reassessment worklist.

    Severity shows in the left rail and the numeral only — no row ever fills
    with colour, so the eye lands on the few that matter instead of a wall of
    red. `meta` items are separate spans, spaced rather than punctuated.
    """
    sel = " qrow--selected" if selected else ""
    meta_html = "".join(f"<span>{escape(str(m))}</span>" for m in meta)
    return (
        f'<div class="qrow qrow--{band_key}{sel}">'
        f'<div class="qrow__rank">{rank:02d}</div>'
        f'<div class="qrow__who">'
        f'<div class="qrow__name">{escape(name)}</div>'
        f'<div class="qrow__cc">{escape(complaint)}</div>'
        f'<div class="qrow__meta">{meta_html}</div></div>'
        f'<div class="qrow__news"><span class="qrow__news-val">{news2}</span>'
        f"<small>NEWS2</small></div>"
        f'<div class="qrow__delta">{delta_chip(delta)}</div>'
        f'<div class="qrow__due"><span>Recheck</span>{escape(due)}</div>'
        f"</div>"
    )


# --- Alert card -------------------------------------------------------------

def alert_card(why: str, reasons: list[str], interval_note: str = "",
               fired: bool = True) -> str:
    """Gemma's sentence on top, the rule that fired underneath.

    The receipt is not collapsible. A nurse must always be able to see
    *"alerted because the RR component hit 3"* without clicking anything.
    """
    receipt = "".join(f"<code>{escape(r)}</code>" for r in reasons)
    foot = f'<p class="t-small alert__foot">{escape(interval_note)}</p>' if interval_note else ""
    head = (
        f'{pill("escalate", "Recheck now")}{ai_tag()}' if fired
        else f'{pill("stable", "No rule fired")}{ai_tag()}'
    )
    return (
        f'<div class="alert{"" if fired else " alert--calm"}">'
        f'<div class="alert__top">{head}</div>'
        f'<p class="alert__why">{escape(why)}</p>'
        f'<div class="alert__rule"><span class="alert__rule-label">Triggered by</span>'
        f'<span class="alert__codes">{receipt}</span></div>'
        f"{foot}</div>"
    )


def card(inner_html: str, extra: str = "") -> str:
    """Escape hatch for pre-built markup that needs the card shell."""
    return f'<div class="card {extra}">{inner_html}</div>'


# --- Agent brief ------------------------------------------------------------

def agent_brief(brief: dict, reasons: list[str], fired: bool) -> str:
    """Gemma's reassessment brief, with the deterministic receipt beneath it.

    The brief is the substance; the receipt is the proof. Both stay visible —
    a nurse must be able to see which rule fired without clicking anything.
    """
    generated = brief.get("_source") == "gemma"
    tag = ai_tag("Generated by Gemma" if generated else "Rule-derived brief")
    status = pill("escalate", "Recheck now") if fired else pill("stable", "No rule fired")

    checks = "".join(
        f'<li><span class="brief__tick">{i}</span>{escape(c)}</li>'
        for i, c in enumerate(brief.get("focus_checks", []), 1)
    )
    receipt = "".join(f"<code>{escape(r)}</code>" for r in (reasons or ["no rule fired"]))
    note = brief.get("_note")
    note_html = f'<p class="brief__note">{escape(note)}</p>' if note else ""

    return (
        f'<div class="brief{"" if fired else " brief--calm"}">'
        f'<div class="brief__top">{status}{tag}</div>'
        f'<p class="brief__headline">{escape(brief.get("headline", ""))}</p>'
        f'<div class="brief__grid">'
        f'<section class="brief__block"><h4>What changed</h4>'
        f'<p>{escape(brief.get("why_now", ""))}</p></section>'
        f'<section class="brief__block"><h4>Check these first</h4>'
        f'<ol class="brief__checks">{checks}</ol></section>'
        f'<section class="brief__block"><h4>History in context</h4>'
        f'<p>{escape(brief.get("history_note", ""))}</p></section>'
        f'<section class="brief__block"><h4>Why this window</h4>'
        f'<p>{escape(brief.get("interval_rationale", ""))}</p></section>'
        f"</div>"
        f'<div class="brief__rule"><span class="brief__rule-label">Escalation decided by</span>'
        f'<span class="brief__codes">{receipt}</span></div>'
        f"{note_html}</div>"
    )


# --- Countdown --------------------------------------------------------------

def countdown(minutes_left: float, interval_min: int) -> str:
    """Live recheck clock. Overdue reads as overdue, in red, with no rounding
    that could make a missed check look like a met one."""
    overdue = minutes_left < 0
    mins = int(abs(minutes_left))
    label = "Overdue by" if overdue else "Recheck in"
    unit = "minute" if mins == 1 else "minutes"
    mod = " countdown--overdue" if overdue else (
        " countdown--soon" if minutes_left <= max(2, interval_min * 0.2) else ""
    )
    return (
        f'<div class="countdown{mod}">'
        f'<span class="countdown__label">{label}</span>'
        f'<span class="countdown__value">{mins} <small>{unit}</small></span>'
        f'<span class="countdown__sub">window of {interval_min} min</span>'
        f"</div>"
    )


# --- Method page ------------------------------------------------------------

def rule_list(title: str, lead: str, rules: list[tuple[str, str]],
              tone: str = "escalate") -> str:
    """Numbered rules, each with its plain-language consequence."""
    items = "".join(
        f'<li class="rule"><span class="rule__n">{i:02d}</span>'
        f'<span class="rule__body"><b>{escape(head)}</b>'
        f'<span class="rule__sub">{escape(sub)}</span></span></li>'
        for i, (head, sub) in enumerate(rules, 1)
    )
    return (
        f'<div class="card panel panel--{tone}">'
        f'<h3 class="t-h3">{escape(title)}</h3>'
        f'<p class="t-small panel__lead">{escape(lead)}</p>'
        f'<ol class="rules">{items}</ol></div>'
    )


def split_panel(title: str, lead: str, rows: list[tuple[str, str, str]]) -> str:
    """Who-does-what table: (actor, does, never)."""
    body = "".join(
        f'<div class="split__row">'
        f'<div class="split__actor">{escape(actor)}</div>'
        f'<div class="split__does">{escape(does)}</div>'
        f'<div class="split__never">{escape(never)}</div></div>'
        for actor, does, never in rows
    )
    return (
        f'<div class="card panel">'
        f'<h3 class="t-h3">{escape(title)}</h3>'
        f'<p class="t-small panel__lead">{escape(lead)}</p>'
        f'<div class="split">'
        f'<div class="split__head"><div></div><div>Decides</div><div>Never does</div></div>'
        f"{body}</div></div>"
    )


def flow_steps(steps: list[tuple[str, str]]) -> str:
    """The monitor loop as a horizontal sequence."""
    items = "".join(
        f'<div class="flow__step"><span class="flow__n">{i}</span>'
        f'<b>{escape(head)}</b><span>{escape(sub)}</span></div>'
        for i, (head, sub) in enumerate(steps, 1)
    )
    return f'<div class="flow">{items}</div>'
