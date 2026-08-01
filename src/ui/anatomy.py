"""The anatomy figure — a rendering of the NEWS2 audit trail, not decoration.

Every organ zone is filled from its own NEWS2 component subscore, so the
figure cannot show anything the deterministic rules did not compute. If the
lungs are red, `resp`/`spo2`/`o2` scored 3. Nothing here is model output.

Body outline is a CC0 anatomical silhouette (see body_asset.py). Organ
geometry below is authored in the same 148 x 318 coordinate space.

Zones stay invisible at score 0 — only what actually scores draws the eye.
"""

from severity import ZONE_LABELS, ZONE_ORDER, zone_levels

from .body_asset import BODY, EARS, TRANSFORM, VIEWBOX

# --- Organ geometry, authored against the body's coordinate space -----------
# Thorax spans y 60-105; lungs leave a mediastinal gap at x 70-76 so the heart
# stays a distinct shape when both are escalating.

_LUNG_L = (
    "M70 63 c-8 -1 -14 2 -17 9 c-3 9 -3 20 -1 29"
    "c1 6 5 9 9 7 c4 -2 8 -8 8 -15 c1 -10 1 -20 1 -30 z"
)
_LUNG_R = (
    "M76 63 c8 -1 14 2 17 9 c3 9 3 20 1 29"
    "c-1 6 -5 9 -9 7 c-4 -2 -8 -8 -8 -15 c-1 -10 -1 -20 -1 -30 z"
)
_HEART = (
    "M73 76 c6 -2 12 1 13 8 c2 7 -1 14 -6 18"
    "c-3 2 -6 2 -9 0 c-6 -3 -9 -10 -7 -16 c1 -6 4 -9 9 -10 z"
)
_VESSELS = (
    "M73 78 C73 70 75 65 81 63"
    "M70 78 C67 70 63 65 57 64"
    "M74 102 L74 140"
    "M74 140 C74 148 70 152 65 155"
    "M74 140 C74 148 78 152 83 155"
)
_HEAD = {"cx": "73", "cy": "24", "rx": "13", "ry": "15"}

# score -> (colour var, fill opacity, stroke opacity, extra class)
_PAINT = {
    0: ("--zone-idle",    "0.55", "0",    ""),
    1: ("--sev-watch",    "0.30", "0.55", ""),
    2: ("--sev-watch",    "0.62", "0.9",  ""),
    3: ("--sev-escalate", "0.80", "1",    " zone--escalate"),
}


def _paint(score: int, *, filled: bool = True) -> str:
    score = min(max(int(score), 0), 3)
    var, fill_op, stroke_op, cls = _PAINT[score]
    stroke = f'stroke="var({var})" stroke-opacity="{stroke_op}" stroke-width="0.9"'
    if not filled:
        return f'class="zone{cls}" fill="none" {stroke.replace("0.9", "1.8")}'
    return f'class="zone{cls}" fill="var({var})" fill-opacity="{fill_op}" {stroke}'


def body_svg(components: dict[str, int]) -> str:
    """Inline SVG of the figure, zones tinted by their NEWS2 subscores."""
    z = zone_levels(components)
    head, lungs = z["head"]["score"], z["lungs"]["score"]
    heart, vessels, temp = z["heart"]["score"], z["vessels"]["score"], z["body"]["score"]

    # Temperature is whole-body, so it colours the OUTLINE, not the fill.
    # Washing the silhouette reads as skin tone and drowns the organ zones.
    temp = min(max(int(temp), 0), 3)
    outline = "var(--body-line)" if temp == 0 else f"var({_PAINT[temp][0]})"
    outline_w = "0.7" if temp == 0 else "1.6"

    return f"""
<svg class="figure__svg" viewBox="{VIEWBOX}" role="img"
     aria-label="Patient figure with NEWS2 component zones highlighted">
  <g transform="{TRANSFORM}">
    <path d="{BODY}" fill="var(--body-fill)" stroke="{outline}" stroke-width="{outline_w}"/>
    <path d="{EARS}" fill="var(--body-fill)" stroke="{outline}" stroke-width="{outline_w}"/>
  </g>
  <ellipse {" ".join(f'{k}="{v}"' for k, v in _HEAD.items())} {_paint(head)}/>
  <path d="{_LUNG_L}" {_paint(lungs)}/>
  <path d="{_LUNG_R}" {_paint(lungs)}/>
  <path d="{_VESSELS}" {_paint(vessels, filled=False)}/>
  <path d="{_HEART}" {_paint(heart)}/>
</svg>"""


def zone_readout(components: dict[str, int]) -> str:
    """Only the zones that actually scored. Silence is the normal state."""
    z = zone_levels(components)
    rows = []
    for name in ZONE_ORDER:
        zone = z[name]
        if zone["score"] <= 0:
            continue
        rows.append(
            f'<div class="zones__row zones__row--{zone["level"]}">'
            f'<span class="zones__organ">{ZONE_LABELS[name]}</span>'
            f'<span class="zones__src">{zone["source"]}</span>'
            f'<span class="zones__score">{zone["score"]}</span>'
            f"</div>"
        )
    if not rows:
        return '<p class="t-small figure__none">No parameter is scoring.</p>'
    return f'<div class="zones">{"".join(rows)}</div>'


def figure(components: dict[str, int], *, readout: bool = True) -> str:
    """The complete figure block: SVG plus the zones that scored."""
    parts = [body_svg(components)]
    if readout:
        parts.append(zone_readout(components))
    return f'<div class="figure">{"".join(parts)}</div>'
