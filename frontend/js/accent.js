/* Riot Music — Akzentfarbe der Künstlerseiten.
   Gleiche Regeln wie backend/theme.py: Farbton bleibt, Sättigung und
   Helligkeit werden in einen lesbaren Bereich gerückt. Aus der einen Farbe
   werden die Abstufungen (hell, dunkel, Schriftfarbe darauf) abgeleitet. */
(function () {
  "use strict";

  const DEFAULT = "#e4252b";
  const MONO = "#ededed";
  const VARS = ["--accent", "--accent-soft", "--blood", "--on-accent", "--accent-ink", "--accent-rgb"];

  function hexToRgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  const toHex = (rgb) => "#" + rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("");

  function rgbToHsl([r, g, b]) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [h / 6, s, l];
  }
  function hslToRgb([h, s, l]) {
    if (s === 0) return [l * 255, l * 255, l * 255];
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    const f = (t) => {
      if (t < 0) t += 1; if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    return [f(h + 1 / 3) * 255, f(h) * 255, f(h - 1 / 3) * 255];
  }
  function luminance(rgb) {
    const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
  }

  /** Beliebige Farbe → lesbare Akzentfarbe (oder "" = Standard). */
  function normalize(hex) {
    const rgb = hexToRgb(hex);
    if (!rgb) return "";
    let [h, s, l] = rgbToHsl(rgb);
    if (s < 0.08 || l < 0.04 || l > 0.97) return MONO;   // Schwarz/Weiß/Grau
    s = Math.max(s, 0.5);
    l = Math.min(Math.max(l, 0.45), 0.6);
    let out = hslToRgb([h, s, l]);
    while (luminance(out) < 0.12 && l < 0.75) { l += 0.02; out = hslToRgb([h, s, l]); }
    return toHex(out);
  }

  /** Abstufungen für CSS-Variablen. */
  function palette(hex) {
    const rgb = hexToRgb(hex) || hexToRgb(DEFAULT);
    const [h, s, l] = rgbToHsl(rgb);
    const light = luminance(rgb) > 0.36;          // helle Farbe (Gelb, Weiß …)
    const blood = toHex(hslToRgb([h, s, l * 0.4]));
    return {
      "--accent": toHex(rgb),
      "--accent-soft": toHex(hslToRgb([h, s, Math.min(0.72, l + 0.1)])),
      "--blood": blood,
      "--on-accent": light ? "#0b0b0c" : "#ffffff",
      // Akzent als Schrift auf Weiß (z. B. Spenden-Button): bei hellen Farben abdunkeln
      "--accent-ink": light ? blood : toHex(rgb),
      "--accent-rgb": rgb.join(","),
    };
  }

  /** Farbe auf ein Element (Standard: ganze Seite) anwenden; leer = zurücksetzen. */
  function apply(hex, target = document.documentElement) {
    if (!hex) { VARS.forEach((v) => target.style.removeProperty(v)); return; }
    for (const [k, v] of Object.entries(palette(hex))) target.style.setProperty(k, v);
  }

  window.RiotAccent = {
    DEFAULT, normalize, palette, apply,
    PRESETS: [
      ["Rot", "#e4252b"], ["Orange", "#f06a1d"], ["Gelb", "#f2c230"], ["Giftgrün", "#5fd12e"],
      ["Türkis", "#1fc4b0"], ["Blau", "#3b7cf5"], ["Violett", "#9a4cf0"], ["Pink", "#ec3d9a"], ["Schwarz-Weiß", "#ededed"],
    ],
  };
})();
