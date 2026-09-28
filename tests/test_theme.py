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

from app.theme import (
    _base_font_points,
    _base_font_size,
    _blend,
    contrast_ratio,
    muted_color,
    small_font_size,
    tiny_font_size,
    widget_stylesheet,
    with_aa_placeholder,
)

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


class TestMutedColor:
    """P2: secondary text (search placeholder, About credit/GitHub links)
    must clear WCAG AA while still reading as secondary."""

    def test_search_placeholder_clears_aa_on_the_field(self):
        for colors in (LIGHT, DARK):
            muted = muted_color(colors["text"], colors["base"])
            ratio = contrast(muted, colors["base"])
            assert ratio >= 4.5, (
                f"placeholder contrast {ratio:.2f}:1 ({muted} on "
                f"{colors['base']}) must reach 4.5:1 — the audit measured "
                f"~4.0:1"
            )

    def test_about_links_clear_aa_on_the_window(self):
        for colors in (LIGHT, DARK):
            muted = muted_color(colors["window_text"], colors["window"])
            ratio = contrast(muted, colors["window"])
            assert ratio >= 4.5, (
                f"About link contrast {ratio:.2f}:1 ({muted} on "
                f"{colors['window']}) must reach 4.5:1 — the audit measured "
                f"~2.8:1 in light mode"
            )

    def test_result_is_muted_but_not_the_full_text_color(self):
        for colors in (LIGHT, DARK):
            muted = muted_color(colors["text"], colors["base"])
            assert muted != colors["text"], (
                "muted_color must step back from full-strength text"
            )
            # …yet stay strictly stronger than the raw foreground alone would
            # not be: it is a blend, so it must sit between the two endpoints.
            assert (
                min(luminance(colors["text"]), luminance(colors["base"]))
                <= luminance(muted)
                <= max(luminance(colors["text"]), luminance(colors["base"]))
            )

    def test_unreachable_ratio_falls_back_to_full_strength(self):
        # Degenerate case: when even fg-on-bg fails AA, the only honest
        # answer is the strongest color available (never a dimmer one).
        assert muted_color("#777777", "#777777", min_ratio=4.5) == "#777777"

    def test_contrast_ratio_matches_the_reference_implementation(self):
        # theme.contrast_ratio is the production copy; tests/test_theme has
        # kept an independent WCAG implementation since the P1 work.
        for a, b in ((LIGHT["text"], LIGHT["base"]),
                     (DARK["window_text"], DARK["window"]),
                     ("#ffffff", "#000000")):
            assert contrast_ratio(a, b) == contrast(a, b)


class TestPlaceholderPalette:
    """QLineEdit draws its placeholder from the palette's PlaceholderText
    role (stylesheets have no placeholder pseudo-element), so the AA fix has
    to go through the palette — and touch *only* that role."""

    def test_placeholder_role_clears_aa_in_both_palettes(self):
        for colors in (LIGHT, DARK):
            pal = with_aa_placeholder(_palette(colors))
            got = pal.color(QPalette.ColorRole.PlaceholderText).name()
            ratio = contrast(got, colors["base"])
            assert ratio >= 4.5, (
                f"PlaceholderText {got} reaches only {ratio:.2f}:1 against "
                f"the field background {colors['base']}"
            )

    def test_every_other_role_is_left_alone(self):
        pal = with_aa_placeholder(_palette(LIGHT))
        for key, role in _ROLE_OF.items():
            assert pal.color(QPalette.ColorGroup.Active, role).name() == \
                QColor(LIGHT[key]).name(), f"role {key} must not change"


class TestFrozenControlsLookDisabled:
    """The QSS `color:` on fields/checkboxes/radios beat the palette's
    disabled text, so a control frozen by a batch rendered at full strength
    and still read as editable (caught by the P2 screenshot review)."""

    # selector, live-text palette role, the background it sits on
    CASES = (
        ("QLineEdit:disabled", "text", "base"),
        ("QComboBox:disabled", "text", "base"),
        ("QSpinBox:disabled", "text", "base"),
        ("QDoubleSpinBox:disabled", "text", "base"),
        ("QCheckBox:disabled", "window_text", "window"),
        ("QRadioButton:disabled", "window_text", "window"),
    )

    def test_disabled_text_is_muted_but_still_aa_readable(self):
        for colors in (LIGHT, DARK):
            css = _stylesheet(colors)
            for sel, live_key, bg_key in self.CASES:
                got = declaration(rule(css, sel), "color")
                assert got != colors[live_key], (
                    f"{sel} still renders at the live text color — a frozen "
                    f"control would look enabled"
                )
                ratio = contrast(got, colors[bg_key])
                assert ratio >= 4.5, (
                    f"{sel} text {got} reaches only {ratio:.2f}:1 on "
                    f"{bg_key} {colors[bg_key]} (WCAG AA is 4.5)"
                )


class TestRadioIndicator:
    """Light-mode regression from the P2 screenshot review: the Windows style
    painted *no* indicator for the checked radio (only the unchecked circles
    showed), so the selected mode/normalization was invisible."""

    def test_checked_indicator_uses_the_accent(self):
        for colors in (LIGHT, DARK):
            css = _stylesheet(colors)
            body = rule(css, "QRadioButton::indicator")
            assert "border-radius" in body, "the indicator must be drawn"
            normal_bg = declaration(body, "background")
            checked_bg = declaration(
                rule(css, "QRadioButton::indicator:checked"), "background"
            )
            assert checked_bg == colors["highlight"], (
                f"the checked dot must fill with the accent, got {checked_bg}"
            )
            assert checked_bg != normal_bg, "checked must differ from unchecked"

    def test_disabled_checked_indicator_dims_to_mid(self):
        for colors in (LIGHT, DARK):
            dim = declaration(
                rule(_stylesheet(colors),
                     "QRadioButton:disabled::indicator:checked"),
                "background",
            )
            assert dim == colors["mid"]


class TestSecondaryFontSizes:
    """P3: secondary text used hardcoded 7pt/8pt literals.

    A literal ignores the platform base (11pt on macOS), where an '8pt'
    hint is barely smaller than the 9-10pt base text it is supposed to sit
    under. Every secondary size must derive from the base instead.
    """

    def test_small_and_tiny_derive_from_the_base(self):
        base = _base_font_points()
        assert _base_font_size() == f"{base}pt"
        assert small_font_size() == f"{base - 1}pt"
        assert tiny_font_size() == f"{base - 2}pt"
        # The steps stay distinct: collapsing them would flatten the
        # hierarchy the sizes exist to express.
        assert small_font_size() != tiny_font_size() != _base_font_size()

    def test_stylesheet_secondary_rules_use_the_derived_size(self):
        for colors in (LIGHT, DARK):
            css = _stylesheet(colors)
            assert f"font-size: {small_font_size()}" in css, (
                "the About dialog's secondary labels must use the derived "
                "size, not a literal"
            )
            # Remove every derived occurrence: what is left must contain no
            # hardcoded literal at all (on any platform).
            stripped = css.replace(f"font-size: {small_font_size()}", "")
            stripped = stripped.replace(f"font-size: {tiny_font_size()}", "")
            assert "font-size: 7pt" not in stripped
            assert "font-size: 8pt" not in stripped
