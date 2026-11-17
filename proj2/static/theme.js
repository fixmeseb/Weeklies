/*
 * Colour theme switcher.
 *
 * Loaded without `defer` in every page's <head>, so the saved palette is applied
 * before the page paints (no flash of the default colours). The palettes
 * themselves are CSS variable sets in static/style.css, keyed by data-palette
 * on <html>; "classic" is the default and uses no attribute.
 *
 * The choice is saved in this browser only (localStorage). Pages that draw with
 * colours once, like the analytics charts, listen for the "palettechange" event.
 */
(function () {
  var KEY = "weeklies-palette";
  var PALETTES = [
    { id: "classic", name: "Classic", swatch: ["#0b0c10", "#5b8cff", "#29c48a"] },
    { id: "sorbet", name: "Sorbet", swatch: ["#b0f2b4", "#bad7f2", "#f2bac9"] },
    { id: "seaside", name: "Seaside", swatch: ["#9d695a", "#78e0dc", "#d496a7"] },
    { id: "midnight", name: "Midnight Garden", swatch: ["#0d1b1e", "#c3dbc5", "#f2cee6"] },
    { id: "driftwood", name: "Driftwood", swatch: ["#283044", "#78a1bb", "#bfa89e"] },
    { id: "fern", name: "Fern", swatch: ["#36453b", "#c2c1a5", "#f5f9e9"] },
    { id: "blossom", name: "Blossom", swatch: ["#ec91d8", "#ffbeef", "#ffd3da"] },
    { id: "admiral", name: "Admiral", swatch: ["#1b264f", "#274690", "#f5f3f5"] },
    { id: "lagoon", name: "Lagoon", swatch: ["#1b264f", "#44ffd1", "#2c8c99"] },
  ];
  var root = document.documentElement;

  function known(id) {
    for (var i = 0; i < PALETTES.length; i++) if (PALETTES[i].id === id) return PALETTES[i];
    return null;
  }

  function saved() {
    try {
      return localStorage.getItem(KEY);
    } catch (e) {
      return null; // storage blocked: use the default
    }
  }

  function apply(id) {
    var palette = known(id) || PALETTES[0];
    if (palette.id === "classic") root.removeAttribute("data-palette");
    else root.setAttribute("data-palette", palette.id);
    return palette;
  }

  function choose(id) {
    var palette = apply(id);
    try {
      localStorage.setItem(KEY, palette.id);
    } catch (e) {
      /* the choice still applies to this page */
    }
    document.dispatchEvent(new CustomEvent("palettechange", { detail: { palette: palette.id } }));
    return palette;
  }

  var current = apply(saved());

  function swatchStyle(palette) {
    var c = palette.swatch;
    return "background: linear-gradient(90deg, " + c[0] + " 0 33%, " + c[1] + " 33% 66%, " + c[2] + " 66%)";
  }

  function build() {
    // The whole pill opens the list: the native <select> is stretched invisibly over it
    // (see .palette-picker in style.css), and the spans below are what shows.
    var label = document.createElement("label");
    label.className = "palette-picker";
    var swatch = document.createElement("span");
    swatch.className = "palette-swatch";
    swatch.setAttribute("aria-hidden", "true");
    var text = document.createElement("span");
    text.className = "palette-label";
    text.textContent = "Theme";
    text.setAttribute("aria-hidden", "true");
    var name = document.createElement("span");
    name.className = "palette-name";
    name.setAttribute("aria-hidden", "true");
    var select = document.createElement("select");
    select.id = "paletteSelect";
    select.setAttribute("aria-label", "Colour theme");
    PALETTES.forEach(function (p) {
      var option = document.createElement("option");
      option.value = p.id;
      option.textContent = p.name;
      select.appendChild(option);
    });
    function show() {
      swatch.setAttribute("style", swatchStyle(current));
      name.textContent = current.name;
    }
    select.value = current.id;
    show();
    select.addEventListener("change", function () {
      current = choose(select.value);
      show();
    });
    label.appendChild(swatch);
    label.appendChild(text);
    label.appendChild(name);
    label.appendChild(select);

    // Customer pages: in the header nav. Restaurant-owner pages: in the banner's
    // button row, or grouped with Logout so it sits beside it.
    var nav = document.querySelector(".site-header nav");
    var heroNav = document.querySelector(".analytics-nav, .dashboard-nav");
    var logout = document.querySelector(".logout-btn");
    if (nav) {
      nav.appendChild(label);
    } else if (heroNav) {
      label.classList.add("on-hero");
      heroNav.insertBefore(label, heroNav.firstChild);
    } else if (logout && logout.parentNode) {
      label.classList.add("on-hero");
      var group = document.createElement("div");
      group.className = "palette-group";
      logout.parentNode.insertBefore(group, logout);
      group.appendChild(label);
      group.appendChild(logout);
    } else {
      label.classList.add("floating");
      document.body.appendChild(label);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();

  window.WeekliesPalettes = { list: PALETTES, choose: choose };
})();
