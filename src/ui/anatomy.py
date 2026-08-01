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
# Thorax interior spans roughly x 50-96, y 58-104. Lungs leave a mediastinal
# gap so the heart stays a distinct shape when both are escalating, and the
# patient's left lung carries a cardiac notch for it to sit in.

_LUNG_L = (
    "M68 60 C60 60 55 66 53 76 C51 86 52 96 55 102"
    "C59 106 65 104 67 98 C69 90 69 74 68 60 z"
)
_LUNG_R = (
    "M79 60 C87 60 92 66 94 76 C96 86 95 96 92 102"
    "C88 106 83 104 81 98"
    # cardiac notch — the indent the heart occupies
    "C80 94 80 91 83 89 C80 87 79 82 79 60 z"
)
_HEART = (
    "M79 77 C85 75 90 80 90 88 C90 96 86 102 80 103"
    "C76 103 73 99 73 92 C73 84 75 79 79 77 z"
)
_VESSELS = (
    # aortic arch and its head/neck branches
    "M79 77 C78 69 79 64 84 61"
    "M76 78 C73 70 70 65 65 63"
    # descending aorta and the iliac bifurcation
    "M80 100 L78 140"
    "M78 140 C78 148 74 152 69 155"
    "M78 140 C78 148 82 152 87 155"
)
# Cranium only. Reaching down over the jaw made the zone read as a face.
_HEAD = {"cx": "73", "cy": "23", "rx": "13", "ry": "14.5"}

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

    # The torso path ends in a flat horizontal edge at the neck, and the head
    # path's jaw dips below it. Stroking both draws that flat edge straight
    # across the chin, so the head goes on top with an OPAQUE fill to cover
    # it. Opaque also stops the overlap from darkening.
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
