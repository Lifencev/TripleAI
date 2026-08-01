"""Loads the design tokens into a Streamlit page.

Streamlit strips <script> from injected markup, so we cannot flip a
`data-theme` attribute at runtime. Instead we promote the active theme's
block to `:root` in Python before injecting. The dark block sits after the
light block in tokens.css, so when promoted it wins on source order at
equal specificity — no !important, no JS.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st

_TOKENS = Path(__file__).with_name("tokens.css")

_FONT = (
    "@import url('https://fonts.googleapis.com/css2"
    "?family=Urbanist:wght@400;500;600;700&display=swap');"
)

THEMES = ("light", "dark")
_KEY = "theme_mode"


@lru_cache(maxsize=len(THEMES))
def _stylesheet(mode: str) -> str:
    css = _TOKENS.read_text(encoding="utf-8")
    if mode == "dark":
        css = css.replace('[data-theme="dark"] {', ':root, [data-theme="dark"] {', 1)
    return f"{_FONT}\n{css}"


def current_mode() -> str:
    return st.session_state.get(_KEY, "light")


def toggle_mode() -> str:
    """Flip light <-> dark. Returns the new mode."""
    st.session_state[_KEY] = "dark" if current_mode() == "light" else "light"
    return st.session_state[_KEY]


def inject_theme(mode: str | None = None) -> str:
    """Inject the stylesheet. Returns the mode actually applied."""
    mode = mode or current_mode()
    if mode not in THEMES:
        mode = "light"
    st.session_state[_KEY] = mode
    st.markdown(f"<style>{_stylesheet(mode)}</style>", unsafe_allow_html=True)
    return mode
