/*
 * Colour theme and style switcher.
 *
 * Loaded without `defer` in every page's <head>, so the saved choices are applied
 * before the page paints (no flash of the default look). Both live in static/style.css:
 *
 *   - Theme: a palette, a set of CSS colour variables keyed by data-palette on <html>;
 *     "classic" is the default and uses no attribute.
 *   - Style: a whole look keyed by data-style on <html>. "standard" uses no attribute;
 *     "almanac" (Seed Catalog & Almanac) brings its own fonts and draws the calendar as
 *     almanac pages. It prints every theme on paper: each palette has a paper version
 *     in style.css (Classic's is the original paper and ink), and its "paper" swatch
 *     here is what the picker shows while that style is on. "ticket" (Kitchen Ticket),
 *     "primer" (Primer) and "menuboard" (Menu Board) bring their own fonts and shapes
 *     but keep each palette's own colours.
 *
 * Choices are saved in this browser only (localStorage). Pages that draw with colours
 * once, like the analytics charts, listen for the "palettechange" event, which also
 * fires when the style changes.
 */
(function () {
  var KEY = "weeklies-palette";
  var STYLE_KEY = "weeklies-style";
  var PALETTES = [
    { id: "classic", name: "Classic", swatch: ["#0b0c10", "#5b8cff", "#29c48a"],
      paper: ["#ece2c9", "#2a2118", "#435f31"] },
    { id: "sorbet", name: "Sorbet", swatch: ["#b0f2b4", "#bad7f2", "#f2bac9"],
      paper: ["#e8ecd6", "#2f6b3f", "#a24d66"] },
    { id: "seaside", name: "Seaside", swatch: ["#9d695a", "#78e0dc", "#d496a7"],
      paper: ["#dfe8e3", "#7d4f42", "#23716d"] },
    { id: "midnight", name: "Midnight Garden", swatch: ["#0d1b1e", "#c3dbc5", "#f2cee6"],
      paper: ["#e8dcb9", "#1f4148", "#864470"] },
    { id: "driftwood", name: "Driftwood", swatch: ["#283044", "#78a1bb", "#bfa89e"],
      paper: ["#e4e3d9", "#283044", "#4a6a80"] },
    { id: "fern", name: "Fern", swatch: ["#36453b", "#c2c1a5", "#f5f9e9"],
      paper: ["#e9ebd6", "#36453b", "#6a6845"] },
    { id: "blossom", name: "Blossom", swatch: ["#ec91d8", "#ffbeef", "#ffd3da"],
      paper: ["#f1e1df", "#8f3279", "#a33d82"] },
    { id: "admiral", name: "Admiral", swatch: ["#1b264f", "#274690", "#f5f3f5"],
      paper: ["#e8e5df", "#274690", "#52669f"] },
    { id: "lagoon", name: "Lagoon", swatch: ["#1b264f", "#44ffd1", "#2c8c99"],
      paper: ["#dfe7e2", "#1a6169", "#237580"] },
  ];
  // Styles use "label", not "name", so they are never mistaken for palettes (see test_themes.py)
  var STYLES = [
    { id: "standard", label: "Standard", glyph: "▦" },
    {
      id: "almanac",
      label: "Seed Catalog & Almanac",
      glyph: "❦",
      fonts:
        "https://fonts.googleapis.com/css2?family=IM+Fell+English:ital@0;1&family=IM+Fell+English+SC" +
        "&family=Spectral:ital,wght@0,400;0,600;1,400&display=swap",
    },
    {
      id: "ticket",
      label: "Kitchen Ticket",
      glyph: "#",
      fonts:
        "https://fonts.googleapis.com/css2?family=Anton" +
        "&family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap",
    },
    {
      id: "primer",
      label: "Primer",
      glyph: "●",
      fonts: "https://fonts.googleapis.com/css2?family=Jost:ital,wght@0,400;0,500;0,600;1,400&display=swap",
    },
    {
      id: "menuboard",
      label: "Menu Board",
      glyph: "★",
      fonts:
        "https://fonts.googleapis.com/css2?family=Archivo+Black" +
        "&family=Archivo:wght@400;500;600;700;800&display=swap",
    },
  ];
  var root = document.documentElement;

  function find(list, id) {
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  function load(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null; // storage blocked: use the default
    }
  }

  function store(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      /* the choice still applies to this page */
    }
  }

  function apply(id) {
    var palette = find(PALETTES, id) || PALETTES[0];
    if (palette.id === "classic") root.removeAttribute("data-palette");
    else root.setAttribute("data-palette", palette.id);
    return palette;
  }

  function loadFonts(style) {
    if (!style.fonts || document.querySelector('link[data-style-fonts="' + style.id + '"]')) return;
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = style.fonts;
    link.setAttribute("data-style-fonts", style.id);
    (document.head || root).appendChild(link);
  }

  function applyStyle(id) {
    var style = find(STYLES, id) || STYLES[0];
    if (style.id === "standard") root.removeAttribute("data-style");
    else root.setAttribute("data-style", style.id);
    loadFonts(style);
    return style;
  }

  function announce() {
    document.dispatchEvent(
      new CustomEvent("palettechange", { detail: { palette: current.id, style: currentStyle.id } })
    );
  }

  function choose(id) {
    current = apply(id);
    store(KEY, current.id);
    announce();
    return current;
  }

  function chooseStyle(id) {
    currentStyle = applyStyle(id);
    store(STYLE_KEY, currentStyle.id);
    announce();
    return currentStyle;
  }

  var current = apply(load(KEY));
  var currentStyle = applyStyle(load(STYLE_KEY));

  function swatchStyle(palette, style) {
    var c = style.id === "almanac" && palette.paper ? palette.paper : palette.swatch;
    return "background: linear-gradient(90deg, " + c[0] + " 0 33%, " + c[1] + " 33% 66%, " + c[2] + " 66%)";
  }

  // One pill: the whole pill opens the list, because the native <select> is stretched
  // invisibly over it (see .palette-picker in style.css) and the spans are what shows.
  function pill(word, selectId, ariaLabel, options, value) {
    var label = document.createElement("label");
    label.className = "palette-picker";
    var mark = document.createElement("span");
    mark.setAttribute("aria-hidden", "true");
    var text = document.createElement("span");
    text.className = "palette-label";
    text.textContent = word;
    text.setAttribute("aria-hidden", "true");
    var name = document.createElement("span");
    name.className = "palette-name";
    name.setAttribute("aria-hidden", "true");
    var select = document.createElement("select");
    select.id = selectId;
    select.setAttribute("aria-label", ariaLabel);
    options.forEach(function (o) {
      var option = document.createElement("option");
      option.value = o.id;
      option.textContent = o.name || o.label;
      select.appendChild(option);
    });
    select.value = value;
    label.appendChild(mark);
    label.appendChild(text);
    label.appendChild(name);
    label.appendChild(select);
    return { label: label, mark: mark, name: name, select: select };
  }

  function build() {
    var theme = pill("Theme", "paletteSelect", "Colour theme", PALETTES, current.id);
    theme.mark.className = "palette-swatch";
    var style = pill("Style", "styleSelect", "Page style", STYLES, currentStyle.id);
    style.mark.className = "style-glyph";

    function show() {
      // Under the Almanac style the swatch shows the palette's paper version
      theme.mark.setAttribute("style", swatchStyle(current, currentStyle));
      theme.name.textContent = current.name;
      style.mark.textContent = currentStyle.glyph;
      style.name.textContent = currentStyle.label;
      theme.label.title =
        currentStyle.id === "almanac" ? "Printed on " + current.name + " paper" : "";
    }
    show();
    theme.select.addEventListener("change", function () {
      choose(theme.select.value);
      show();
    });
    style.select.addEventListener("change", function () {
      chooseStyle(style.select.value);
      show();
    });

    var set = document.createElement("span");
    set.className = "picker-set";
    set.appendChild(theme.label);
    set.appendChild(style.label);

    // Customer pages: in the header nav. Restaurant-owner pages: in the banner's
    // button row, or grouped with Logout so they sit beside it.
    var nav = document.querySelector(".site-header nav");
    var heroNav = document.querySelector(".analytics-nav, .dashboard-nav");
    var logout = document.querySelector(".logout-btn");
    if (nav) {
      nav.appendChild(set);
    } else if (heroNav) {
      theme.label.classList.add("on-hero");
      style.label.classList.add("on-hero");
      heroNav.insertBefore(set, heroNav.firstChild);
    } else if (logout && logout.parentNode) {
      theme.label.classList.add("on-hero");
      style.label.classList.add("on-hero");
      var group = document.createElement("div");
      group.className = "palette-group";
      logout.parentNode.insertBefore(group, logout);
      group.appendChild(set);
      group.appendChild(logout);
    } else {
      set.classList.add("floating");
      document.body.appendChild(set);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();

  window.WeekliesPalettes = { list: PALETTES, choose: choose };
  window.WeekliesStyles = { list: STYLES, choose: chooseStyle };
})();
