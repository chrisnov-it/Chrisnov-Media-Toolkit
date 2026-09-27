"""Theme stylesheet guarantees — disabled buttons must stay readable (P1).

The disabled rule used to be ``color: {mid}; background: {mid}``: the exact
same palette color for text and surface, i.e. 1.00:1 contrast and an
invisible label on every disabled button (Start, Convert, Clear…). The
replacement derives a blended text color from the *active* palette instead of
Qt's Disabled group — Qt palettes routinely leave that group mirroring Active,
which is exactly how the blue ``#primaryButton`` kept looking enabled.

These tests build the same light/dark palettes the app gets on a theme
change, render the stylesheet, and check the numbers the audit measured by
hand.
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QPalette

from app.theme import _blend, widget_stylesheet

# --- Palette fixtures ------------------------------------------------------

# Values measured from the real system light palette and the constructed dark
# palette during the audit (see the P1 notes in the changelog).
LIGHT = {
    "window": "#f0f0f0", "window_text": "#000000",
    "base": "#ffffff", "text": "#000000",
    "highlight": "#0067c0", "highlighted_text": "#ffffff",
    "button": "#f0f0f0", "button_text": "#000000",
    "mid": "#a0a0a0", "midlight": "#e3e3e3", "dark": "#a0a0a0",
}
DARK = {
    "window": "#353535", "window_text": "#ffffff",
    "base": "#303030", "text": "#ffffff",
    "highlight": "#0067c0", "highlighted_text": "#ffffff",
    "button": "#353535", "button_text": "#ffffff",
    "mid": "#a0a0a0", "midlight": "#484848", "dark": "#232323",
}

_ROLE_OF = {
    "window": QPalette.ColorRole.Window,
    "window_text": QPalette.ColorRole.WindowText,
    "base": QPalette.ColorRole.Base,
    "text": QPalette.ColorRole.Text,
    "highlight": QPalette.ColorRole.Highlight,
    "highlighted_text": QPalette.ColorRole.HighlightedText,
    "button": QPalette.ColorRole.Button,
    "button_text": QPalette.ColorRole.ButtonText,
    "mid": QPalette.ColorRole.Mid,
    "midlight": QPalette.ColorRole.Midlight,
    "dark": QPalette.ColorRole.Dark,
}


def _palette(colors: dict[str, str]) -> QPalette:
    """Build a palette with *colors* set on the Active group.

    widget_stylesheet() reads QPalette.ColorGroup.Active only, which is also
    why the Disabled group cannot be trusted to carry a disabled text color.
    """
    pal = QPalette()
    for key, rgb in colors.items():
        pal.setColor(QPalette.ColorGroup.Active, _ROLE_OF[key], QColor(rgb))
    return pal


def _stylesheet(colors: dict[str, str]) -> str:
    return widget_stylesheet(_palette(colors))


# --- Contrast helpers ------------------------------------------------------

def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two ``#rrggbb`` colors (1.0 - 21.0)."""
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def rule(css: str, selector: str) -> str:
    """Return the declaration body of *selector*'s first matching rule."""
    match = re.search(
        rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", css, flags=re.DOTALL
    )
    assert match is not None, f"stylesheet is missing a {selector!r} rule"
    return match.group(1)


def declaration(body: str, property_name: str) -> str:
    """Read a color-valued declaration from *body* (``background`` is also
    accepted when *property_name* is ``background-color`` — the stylesheet
    uses the short form)."""
    if property_name == "background-color":
        pattern = r"(?:background-color|background):\s*(#\w+|transparent)"
    else:
        pattern = rf"{property_name}:\s*(#\w+|transparent)"
    match = re.search(pattern, body)
    assert match is not None, (
        f"expected a '{property_name}' declaration in rule body:\n{body}"
    )
    return match.group(1)


# --- Tests -----------------------------------------------------------------

class TestBlend:
    def test_endpoints(self):
        assert _blend("#000000", "#ffffff", 0.0) == "#000000"
        assert _blend("#000000", "#ffffff", 1.0) == "#ffffff"

    def test_midpoint_is_the_average(self):
        assert _blend("#000000", "#f0f0f0", 0.5) == "#787878"

    def test_result_stays_inside_the_two_colors(self):
        out = _blend("#ffffff", "#353535", 0.45)
        assert out.startswith("#") and len(out) == 7
        # Dimmer than white, brighter than the surface — a muted middle.
        assert luminance("#ffffff") > luminance(out) > luminance("#353535")


class TestDisabledButtons:
    """The P1 regression: disabled labels must be readable, not mid-on-mid."""

    def test_disabled_rule_never_uses_the_same_color_for_text_and_bg(self):
        for colors in (LIGHT, DARK):
            body = rule(_stylesheet(colors), "QPushButton:disabled")
            text = declaration(body, "color")
            bg = declaration(body, "background-color")
            assert text != bg, (
                f"disabled label is invisible in this palette: "
                f"text == background == {text}"
            )

    def test_disabled_label_contrast_is_wcag_aa(self):
        # The audit measured 1.00:1 before the fix; AA for normal text is 4.5.
        for colors in (LIGHT, DARK):
            body = rule(_stylesheet(colors), "QPushButton:disabled")
            text = declaration(body, "color")
            bg = declaration(body, "background-color")
            ratio = contrast(text, bg)
            assert ratio >= 4.5, (
                f"disabled label contrast {ratio:.2f}:1 ({text} on {bg}) "
                f"must reach 4.5:1 (button background {colors['button']})"
            )

    def test_primary_disabled_loses_its_blue(self):
        # Qt gives ID selectors higher specificity than :disabled, so without
        # an explicit rule the blue #primaryButton wins and the button looks
        # enabled. Both palettes: no highlight color may survive.
        for colors in (LIGHT, DARK):
            body = rule(_stylesheet(colors), "QPushButton#primaryButton:disabled")
            bg = declaration(body, "background-color")
            assert bg == colors["button"], (
                f"a disabled primary button must fall back to the neutral "
                f"surface, got {bg}"
            )
            ratio = contrast(declaration(body, "color"), bg)
            assert ratio >= 4.5, f"disabled primary label contrast {ratio:.2f}:1"

    def test_danger_disabled_loses_its_high_contrast_text(self):
        for colors in (LIGHT, DARK):
            body = rule(_stylesheet(colors), "QPushButton#dangerButton:disabled")
            text = declaration(body, "color")
            # transparent background → the label sits on the window surface
            assert declaration(body, "background-color") == "transparent"
            ratio = contrast(text, colors["window"])
            assert ratio >= 4.5, (
                f"disabled danger label contrast {ratio:.2f}:1 ({text} on "
                f"{colors['window']})"
            )

    def test_disabled_rules_come_after_the_hover_rules(self):
        # Equal-specificity ties (and Qt's per-property resolution) favour
        # the later rule, so :disabled must not be shadowed by :hover.
        for colors in (LIGHT, DARK):
            css = _stylesheet(colors)
            assert css.index("QPushButton:disabled") > css.index("QPushButton:hover")
            assert css.index("QPushButton#primaryButton:disabled") > css.index(
                "QPushButton#primaryButton:hover"
            )
            assert css.index("QPushButton#dangerButton:disabled") > css.index(
                "QPushButton#dangerButton:hover"
            )


class TestEnabledButtonsStillRender:
    """Guards the other direction: the P1 rules must not mute live buttons."""

    def test_enabled_primary_keeps_the_accent_background(self):
        css = _stylesheet(LIGHT)
        body = rule(css, "QPushButton#primaryButton")
        assert declaration(body, "background-color") == LIGHT["highlight"]
