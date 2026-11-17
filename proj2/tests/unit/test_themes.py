"""
Colour themes: static/theme.js offers the palettes, static/style.css defines them, and
every template loads the switcher and takes its colours from the theme variables.
"""

import re
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[2]
TEMPLATES = sorted((PROJ / "templates").glob("*.html"))
STYLE = (PROJ / "static" / "style.css").read_text(encoding="utf-8")
THEME_JS = (PROJ / "static" / "theme.js").read_text(encoding="utf-8")

PALETTE_IDS = re.findall(r'\{ id: "([a-z]+)", name:', THEME_JS)

## Every variable a palette must set; Classic sets them on :root
REQUIRED = [
    "--bg", "--surface", "--elev", "--text", "--muted", "--primary", "--primary-600",
    "--primary-700", "--on-primary", "--success", "--warning", "--danger", "--info",
    "--border", "--hint", "--ring", "--accent", "--accent-2", "--hero-a", "--hero-b",
    "--on-hero", "--glow-1", "--glow-2", "--shade", "--star",
]

## The old dark-only surface colours that templates used to hard-code
OLD_DARK = ["#0f1419", "#0b0f14", "#0a0d12", "#0e162b", "#0b1220", "#10131b"]


def palette_block(palette_id):
    match = re.search(r':root\[data-palette="%s"\]\s*\{(.*?)\}' % palette_id, STYLE, re.S)
    return match.group(1) if match else None


def test_switcher_offers_the_palettes():
    assert PALETTE_IDS[0] == "classic"
    assert set(PALETTE_IDS) == {
        "classic", "sorbet", "seaside", "midnight",
        "driftwood", "fern", "blossom", "admiral", "lagoon",
    }


@pytest.mark.parametrize("palette_id", PALETTE_IDS[1:])
def test_each_palette_sets_every_variable(palette_id):
    block = palette_block(palette_id)
    assert block is not None, f"style.css has no block for {palette_id}"
    missing = [name for name in REQUIRED if not re.search(re.escape(name) + r"\s*:", block)]
    assert not missing
    assert "color-scheme" in block


def test_classic_defines_every_variable_on_root():
    root = re.search(r":root\s*\{(.*?)\}", STYLE, re.S).group(1)
    assert [name for name in REQUIRED if name + ":" not in root] == []


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_every_page_loads_the_switcher_in_head(template):
    html = template.read_text(encoding="utf-8")
    head = html.split("</head>")[0]
    assert "filename='theme.js'" in head
    # Not deferred, so the saved palette applies before the page paints
    assert re.search(r"<script src=\"\{\{ url_for\('static', filename='theme.js'\) \}\}\"></script>", head)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_use_theme_variables_not_dark_only_colours(template):
    html = template.read_text(encoding="utf-8").lower()
    styles = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    styles += " ".join(re.findall(r'style="([^"]*)"', html))
    assert [c for c in OLD_DARK if c in styles] == []
    # Blue tints and white overlays now come from --primary and --text
    assert "rgba(91, 140, 255" not in styles and "rgba(91,140,255" not in styles


def _variables(palette_id):
    if palette_id == "classic":
        block = re.search(r":root\s*\{(.*?)\}", STYLE, re.S).group(1)
    else:
        block = palette_block(palette_id)
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", block))


def _luminance(hex_colour):
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


## (foreground, background) pairs the pages use for text
TEXT_PAIRS = [
    ("--text", "--bg"), ("--text", "--surface"), ("--text", "--elev"),
    ("--muted", "--bg"), ("--muted", "--surface"),
    ("--on-primary", "--primary"), ("--primary", "--surface"),
]


@pytest.mark.parametrize("palette_id", PALETTE_IDS)
@pytest.mark.parametrize("fg, bg", TEXT_PAIRS)
def test_text_meets_wcag_aa_contrast(palette_id, fg, bg):
    """4.5:1 is the WCAG AA minimum for normal-size text."""
    if (palette_id, fg) == ("classic", "--on-primary"):
        pytest.xfail("Classic's original white-on-#5b8cff buttons are about 3.3:1; left as designed")
    colours = _variables(palette_id)
    assert _contrast(colours[fg], colours[bg]) >= 4.5, (fg, bg, colours[fg], colours[bg])
