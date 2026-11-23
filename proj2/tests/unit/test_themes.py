"""
Colour themes: static/theme.js offers the palettes, static/style.css defines them, and
every template loads the switcher and takes its colours from the theme variables.
"""

import re
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parents[2]
# Full pages only: "_name.html" files are pieces included into pages
TEMPLATES = sorted(p for p in (PROJ / "templates").glob("*.html") if not p.name.startswith("_"))
STYLE = (PROJ / "static" / "style.css").read_text(encoding="utf-8")
THEME_JS = (PROJ / "static" / "theme.js").read_text(encoding="utf-8")

PALETTE_IDS = re.findall(r'\{ id: "([a-z]+)", name:', THEME_JS)

## Every variable a palette must set; Classic sets them on :root
REQUIRED = [
    "--bg",
    "--surface",
    "--elev",
    "--text",
    "--muted",
    "--primary",
    "--primary-600",
    "--primary-700",
    "--on-primary",
    "--success",
    "--warning",
    "--danger",
    "--info",
    "--border",
    "--hint",
    "--ring",
    "--accent",
    "--accent-2",
    "--hero-a",
    "--hero-b",
    "--on-hero",
    "--glow-1",
    "--glow-2",
    "--shade",
    "--star",
]

## The old dark-only surface colours that templates used to hard-code
OLD_DARK = ["#0f1419", "#0b0f14", "#0a0d12", "#0e162b", "#0b1220", "#10131b"]


def palette_block(palette_id):
    match = re.search(r':root\[data-palette="%s"\]\s*\{(.*?)\}' % palette_id, STYLE, re.S)
    return match.group(1) if match else None


def test_switcher_offers_the_palettes():
    assert PALETTE_IDS[0] == "classic"
    assert set(PALETTE_IDS) == {
        "classic",
        "sorbet",
        "seaside",
        "midnight",
        "driftwood",
        "fern",
        "blossom",
        "admiral",
        "lagoon",
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
    assert re.search(
        r"<script src=\"\{\{ url_for\('static', filename='theme.js'\) \}\}\"></script>", head
    )


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_use_theme_variables_not_dark_only_colours(template):
    html = template.read_text(encoding="utf-8").lower()
    styles = " ".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    styles += " ".join(re.findall(r'style="([^"]*)"', html))
    assert [c for c in OLD_DARK if c in styles] == []
    # Blue tints and white overlays now come from --primary and --text
    assert "rgba(91, 140, 255" not in styles and "rgba(91,140,255" not in styles


def style_block(style_id):
    match = re.search(r':root\[data-style="%s"\]\s*\{(.*?)\}' % style_id, STYLE, re.S)
    return match.group(1) if match else None


def test_switcher_offers_the_almanac_style():
    assert re.findall(r'\{ id: "([a-z]+)", label:', THEME_JS) == ["standard"]
    assert 'id: "almanac",' in THEME_JS and 'label: "Seed Catalog & Almanac"' in THEME_JS


def test_almanac_style_sets_every_variable():
    """The Almanac style's own block is Classic on paper, so it sets everything a palette does."""
    block = style_block("almanac")
    assert block is not None
    assert [name for name in REQUIRED if not re.search(re.escape(name) + r"\s*:", block)] == []
    assert "color-scheme" in block


def test_almanac_style_overrides_the_palettes():
    """Same specificity as the palette blocks, so it must come after all of them (it is
    Classic's paper version, and the base the other paper versions build on)."""
    assert STYLE.index(':root[data-style="almanac"] {') > max(
        STYLE.index(f':root[data-palette="{p}"]') for p in PALETTE_IDS[1:]
    )


def paper_block(palette_id):
    match = re.search(
        r':root\[data-style="almanac"\]\[data-palette="%s"\]\s*\{(.*?)\}' % palette_id,
        STYLE,
        re.S,
    )
    return match.group(1) if match else None


## The paper versions keep the Almanac block's transparent glows and its shadows
PAPER_REQUIRED = [name for name in REQUIRED if not name.startswith("--glow")]


@pytest.mark.parametrize("palette_id", PALETTE_IDS[1:])
def test_each_palette_has_a_paper_version(palette_id):
    """Under Seed Catalog & Almanac every theme prints on its own paper."""
    block = paper_block(palette_id)
    assert block is not None, f"style.css has no paper version of {palette_id}"
    missing = [name for name in PAPER_REQUIRED if not re.search(re.escape(name) + r"\s*:", block)]
    assert not missing


@pytest.mark.parametrize("palette_id", PALETTE_IDS)
def test_switcher_has_a_paper_swatch_for_each_palette(palette_id):
    entry = re.search(r'\{ id: "%s", name: [^}]*\}' % palette_id, THEME_JS).group(0)
    paper = re.search(r"paper: \[([^\]]+)\]", entry)
    assert paper, f"{palette_id} has no paper swatch"
    bg = _variables("almanac-style" if palette_id == "classic" else f"paper-{palette_id}")["--bg"]
    assert paper.group(1).split(",")[0].strip().strip('"') == bg


def test_theme_picker_stays_usable_under_the_almanac_style():
    assert "select.disabled" not in THEME_JS


def _variables(palette_id):
    if palette_id == "classic":
        block = re.search(r":root\s*\{(.*?)\}", STYLE, re.S).group(1)
    elif palette_id == "almanac-style":
        block = style_block("almanac")
    elif palette_id.startswith("paper-"):
        # The paper version over the Almanac block it builds on
        base = dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", style_block("almanac")))
        own = re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", paper_block(palette_id[6:]))
        return {**base, **dict(own)}
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
    ("--text", "--bg"),
    ("--text", "--surface"),
    ("--text", "--elev"),
    ("--muted", "--bg"),
    ("--muted", "--surface"),
    ("--on-primary", "--primary"),
    ("--primary", "--surface"),
]


@pytest.mark.parametrize("palette_id", PALETTE_IDS + ["almanac-style"])
@pytest.mark.parametrize("fg, bg", TEXT_PAIRS)
def test_text_meets_wcag_aa_contrast(palette_id, fg, bg):
    """4.5:1 is the WCAG AA minimum for normal-size text."""
    if (palette_id, fg) == ("classic", "--on-primary"):
        pytest.xfail(
            "Classic's original white-on-#5b8cff buttons are about 3.3:1; left as designed"
        )
    colours = _variables(palette_id)
    assert _contrast(colours[fg], colours[bg]) >= 4.5, (fg, bg, colours[fg], colours[bg])


PAPER_IDS = ["almanac-style"] + [f"paper-{p}" for p in PALETTE_IDS[1:]]

## The Almanac style also prints display headings in --primary on the page, status words
## on cards, and the restaurant banner in --hero-*.
PAPER_TEXT_PAIRS = TEXT_PAIRS + [
    ("--primary", "--bg"),
    ("--muted", "--elev"),
    ("--success", "--surface"),
    ("--warning", "--surface"),
    ("--danger", "--surface"),
    ("--info", "--surface"),
    ("--on-hero", "--hero-a"),
    ("--on-hero", "--hero-b"),
]


@pytest.mark.parametrize("palette_id", PAPER_IDS)
@pytest.mark.parametrize("fg, bg", PAPER_TEXT_PAIRS)
def test_paper_versions_meet_wcag_aa_contrast(palette_id, fg, bg):
    colours = _variables(palette_id)
    assert _contrast(colours[fg], colours[bg]) >= 4.5, (fg, bg, colours[fg], colours[bg])


@pytest.mark.parametrize("palette_id", PAPER_IDS)
@pytest.mark.parametrize(
    "fg, bg", [("--accent", "--bg"), ("--border", "--bg"), ("--star", "--surface")]
)
def test_paper_ornaments_and_rules_are_visible(palette_id, fg, bg):
    """Ornaments, stars and ruled lines are not body text; 3:1 for ornaments and stars
    (WCAG non-text contrast), and rules need only stand out from the paper."""
    colours = _variables(palette_id)
    minimum = 1.4 if fg == "--border" else 3.0
    assert _contrast(colours[fg], colours[bg]) >= minimum, (fg, bg, colours[fg], colours[bg])


## Styles that keep each palette's own colours and change only type and shapes
COLOUR_KEEPING_STYLES = {
    "ticket": ("Kitchen Ticket", ["Anton", "IBM+Plex+Mono"]),
    "primer": ("Primer", ["Jost"]),
    "menuboard": ("Menu Board", ["Archivo+Black", "Archivo:"]),
}


def _style_entry(style_id):
    match = re.search(r'\{\s*id: "%s",\s*label: "([^"]+)",(.*?)\n    \}' % style_id, THEME_JS, re.S)
    return match


def test_switcher_offers_every_style_in_order():
    assert re.findall(r'id: "([a-z]+)",\s*label:', THEME_JS) == [
        "standard",
        "almanac",
        "ticket",
        "primer",
        "menuboard",
    ]


@pytest.mark.parametrize("style_id", COLOUR_KEEPING_STYLES)
def test_new_style_is_offered_with_its_fonts(style_id):
    label, families = COLOUR_KEEPING_STYLES[style_id]
    entry = _style_entry(style_id)
    assert entry, f"theme.js does not offer {style_id}"
    assert entry.group(1) == label
    fonts = "".join(re.findall(r'"([^"]*)"', entry.group(2).split("fonts:")[1]))
    assert fonts.startswith("https://fonts.googleapis.com/css2?")
    assert all(family in fonts for family in families)


@pytest.mark.parametrize("style_id", COLOUR_KEEPING_STYLES)
def test_new_style_sets_its_type_and_keeps_the_palette_colours(style_id):
    """These styles work on all nine themes because they never redefine a colour."""
    block = style_block(style_id)
    assert block is not None, f"style.css has no block for {style_id}"
    assert "--font:" in block and "--font-display:" in block
    assert [name for name in REQUIRED if re.search(re.escape(name) + r"\s*:", block)] == []
    assert not re.search(r':root\[data-style="%s"\]\[data-palette=' % style_id, STYLE)


@pytest.mark.parametrize("style_id", COLOUR_KEEPING_STYLES)
def test_new_style_draws_only_with_theme_variables(style_id):
    rules = re.findall(r':root[^{]*data-style="%s"[^{]*\{([^}]*)\}' % style_id, STYLE)
    assert rules
    assert [r for r in rules if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", r)] == []


@pytest.mark.parametrize("palette_id", PALETTE_IDS)
@pytest.mark.parametrize("status", ["--success", "--warning", "--danger", "--info"])
def test_menu_board_status_tags_are_readable(palette_id, status):
    """Menu Board prints order statuses as --bg text on a tag of the status colour."""
    colours = _variables(palette_id)
    assert _contrast(colours["--bg"], colours[status]) >= 4.5, (status, colours[status])


@pytest.mark.parametrize("palette_id", PALETTE_IDS)
def test_menu_board_today_board_is_readable(palette_id):
    """Its board is --text with --bg lettering, and the combo numbers swap the two."""
    colours = _variables(palette_id)
    assert _contrast(colours["--bg"], colours["--text"]) >= 4.5
