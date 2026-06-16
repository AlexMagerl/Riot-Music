/* Riot Music — Frontend-SPA
   Hash-basiertes Routing, JSON-API, persistenter Audio-Player mit Warteschlange. */
"use strict";

const api = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  },
  platform: () => api.get("/api/platform"),
  genres: () => api.get("/api/genres"),
  artists: (genre) => api.get("/api/artists" + (genre ? `?genre=${encodeURIComponent(genre)}` : "")),
  artist: (id) => api.get(`/api/artists/${encodeURIComponent(id)}`),
  radio: () => api.get("/api/radio"),
  search: (q, genre) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (genre) p.set("genre", genre);
    return api.get(`/api/search?${p.toString()}`);
  },
};

/* ---------- Helfer ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
};

function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// deterministische Farbe aus einem String (für Cover-Kacheln)
function colorOf(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360;
  return `linear-gradient(135deg, hsl(${h} 62% 38%), hsl(${(h + 40) % 360} 64% 24%))`;
}
const initials = (name) => name.split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();

/* ---------- Globaler Zustand ---------- */
const state = { genres: [], platform: null };

/* ==================================================================
   PLAYER
   ================================================================== */
const audio = $("#audio");
const player = {
  queue: [],
  index: -1,
  radio: false,            // Endlos-Zufallsmodus
  loopMode: "off",         // "off" | "all" | "one"
  playCountRecorded: false, // Wurde der Play nach 30 Sekunden gezählt?

  setQueue(tracks, startIndex = 0, radio = false) {
    this.queue = tracks;
    this.index = startIndex;
    this.radio = radio;
    this.load(true);
  },

  async startRadio() {
    let tracks = [];
    try { tracks = await api.radio(); } catch { tracks = []; }
    if (!tracks.length) return;
    this.setQueue(tracks, 0, true);
  },

  async refillRadio() {
    try {
      const more = await api.radio();
      if (more.length) this.queue = this.queue.concat(more);
    } catch {}
  },

  load(autoplay) {
    const t = this.queue[this.index];
    if (!t) return;
    audio.src = t.url;
    $("#player-title").textContent = t.title;
    const artistLink = $("#player-artist");
    artistLink.textContent = t.artistName;
    artistLink.href = `#/artist/${t.artistId}`;
    const cover = $("#player-cover");
    cover.innerHTML = "";
    cover.style.background = colorOf(t.artistId);
    if (t.coverThumb || t.cover) cover.appendChild(el("img", { class: "tile-img", src: t.coverThumb || t.cover, alt: "" }));
    else cover.appendChild(document.createTextNode(initials(t.artistName)));
    this.playCountRecorded = false;  // Reset für neuen Track
    updateMediaSession(t);           // Sperrbildschirm-Infos aktualisieren
    if (autoplay) audio.play().catch(() => {});
    highlightPlaying();
  },

  toggle() {
    if (!this.queue.length) return;
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  },

  async next(auto = false) {
    // Bei "Titel wiederholen" nur, wenn der Song von selbst zu Ende lief
    if (auto && this.loopMode === "one") { audio.currentTime = 0; audio.play().catch(() => {}); return; }

    if (this.radio && this.index >= this.queue.length - 2) await this.refillRadio();

    if (this.index < this.queue.length - 1) { this.index++; this.load(true); }
    else if (this.loopMode === "all" && this.queue.length) { this.index = 0; this.load(true); }
    else { audio.pause(); audio.currentTime = 0; }
  },

  prev() {
    if (audio.currentTime > 3) { audio.currentTime = 0; return; }
    if (this.index > 0) { this.index--; this.load(true); }
    else { audio.currentTime = 0; }
  },

  cycleLoop() {
    this.loopMode = this.loopMode === "off" ? "all" : this.loopMode === "all" ? "one" : "off";
    const btn = $("#btn-loop");
    btn.textContent = this.loopMode === "one" ? "🔂" : "🔁";
    btn.classList.toggle("active", this.loopMode !== "off");
    btn.title = "Wiederholen: " +
      (this.loopMode === "off" ? "aus" : this.loopMode === "all" ? "alle" : "ein Titel");
  },

  currentTrackId() {
    const t = this.queue[this.index];
    return t ? t.id : null;
  },
};

function highlightPlaying() {
  const id = player.currentTrackId();
  document.querySelectorAll(".track").forEach((row) => {
    row.classList.toggle("playing", row.dataset.trackId === id && !audio.paused);
  });
}

/* Player-Events */
$("#btn-play").addEventListener("click", () => player.toggle());
$("#btn-next").addEventListener("click", () => player.next());
$("#btn-prev").addEventListener("click", () => player.prev());
$("#btn-loop").addEventListener("click", () => player.cycleLoop());
$("#btn-radio").addEventListener("click", () => player.startRadio());
/* Zählt einen Spenden-Button-Klick (nur Interesse-Signal, kein Betrag). */
function trackDonateClick(artistId) {
  try {
    const body = new URLSearchParams();
    if (artistId) body.set("artistId", artistId);
    // keepalive, damit der Request auch beim Tab-Wechsel zu PayPal durchgeht.
    fetch("/api/stats/donate-click", { method: "POST", body, keepalive: true });
  } catch { /* Tracking darf den Spendenfluss nie blockieren */ }
}

/* Spenden-Button: nur auf Künstlerprofilen mit hinterlegter PayPal-Adresse.
   Geht zu 100% direkt an die jeweilige Künstler:in. */
function hideDonateButton() {
  const btn = $("#btn-donate");
  if (btn) { btn.style.display = "none"; btn.onclick = null; }
}

function showDonateButton(artist) {
  const btn = $("#btn-donate");
  if (!btn) return;
  if (!artist || !artist.donateUrl) { hideDonateButton(); return; }
  btn.textContent = `♥ Spenden für ${artist.name}`;
  btn.title = `Direkt an ${artist.name} spenden (100% via PayPal)`;
  btn.style.display = "";
  btn.onclick = () => { trackDonateClick(artist.id); window.open(artist.donateUrl, "_blank", "noopener"); };
}

// Beim Laden zunächst ausblenden (Startseite hat keinen Künstlerkontext).
hideDonateButton();

/* Geheimer Admin-Zugang: per Shift+A ein-/ausblenden. */
document.addEventListener("keydown", (e) => {
  // Nicht auslösen, während in einem Eingabefeld getippt wird.
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  if (e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey &&
      (e.key === "A" || e.key === "a")) {
    const link = document.getElementById("nav-admin");
    if (!link) return;
    const hidden = link.style.display === "none";
    link.style.display = hidden ? "" : "none";
    toast(hidden ? "Admin-Zugang eingeblendet 🛡" : "Admin-Zugang ausgeblendet");
  }
});

let _toastTimer;
function toast(msg) {
  let t = $("#app-toast");
  if (!t) { t = el("div", { id: "app-toast", class: "app-toast" }); document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

audio.addEventListener("play", () => {
  $("#btn-play").textContent = "⏸"; highlightPlaying();
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "playing";
});
audio.addEventListener("pause", () => {
  $("#btn-play").textContent = "▶"; highlightPlaying();
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "paused";
});
audio.addEventListener("ended", () => player.next(true));

audio.addEventListener("loadedmetadata", () => {
  $("#time-dur").textContent = fmtTime(audio.duration);
  updatePositionState();
});

/* ---- MediaSession: Sperrbildschirm-Steuerung + Hintergrund-Wiedergabe ----
   Liefert Titel/Cover an die System-Medienanzeige und verdrahtet die
   Hardware-/Lockscreen-Tasten. Wichtig für die Android-App (TWA), damit
   Musik bei gesperrtem Bildschirm steuerbar bleibt. */
function updateMediaSession(t) {
  if (!("mediaSession" in navigator) || !t) return;
  const art = t.cover || t.coverThumb;
  const artwork = art
    ? [{ src: new URL(art, location.origin).href, sizes: "512x512", type: "image/jpeg" }]
    : [];
  navigator.mediaSession.metadata = new MediaMetadata({
    title: t.title || "",
    artist: t.artistName || "",
    album: t.releaseTitle || "Riot Music",
    artwork,
  });
}

function updatePositionState() {
  if (!("mediaSession" in navigator) || !("setPositionState" in navigator.mediaSession)) return;
  if (!isFinite(audio.duration) || audio.duration <= 0) return;
  try {
    navigator.mediaSession.setPositionState({
      duration: audio.duration,
      position: Math.min(audio.currentTime, audio.duration),
      playbackRate: audio.playbackRate || 1,
    });
  } catch {}
}

if ("mediaSession" in navigator) {
  const ms = navigator.mediaSession;
  ms.setActionHandler("play", () => audio.play().catch(() => {}));
  ms.setActionHandler("pause", () => audio.pause());
  ms.setActionHandler("previoustrack", () => player.prev());
  ms.setActionHandler("nexttrack", () => player.next());
  try {
    ms.setActionHandler("seekto", (e) => {
      if (e.fastSeek && "fastSeek" in audio) { audio.fastSeek(e.seekTime); return; }
      if (typeof e.seekTime === "number") audio.currentTime = e.seekTime;
    });
  } catch {}
}

const seek = $("#seek");
let seeking = false;
audio.addEventListener("timeupdate", () => {
  if (seeking) return;
  // Play nach 30 Sekunden zählen (einmalig pro Track)
  if (!player.playCountRecorded && audio.currentTime > 30 && player.queue[player.index]) {
    const trackId = player.queue[player.index].id;
    fetch(`/api/plays/${trackId}`, { method: "POST" }).catch(() => {});
    player.playCountRecorded = true;
  }
  const pct = audio.duration ? (audio.currentTime / audio.duration) * 1000 : 0;
  seek.value = pct;
  $("#time-cur").textContent = fmtTime(audio.currentTime);
  seek.style.background =
    `linear-gradient(to right, var(--accent) ${pct / 10}%, var(--border) ${pct / 10}%)`;
  updatePositionState();
});
seek.addEventListener("input", () => { seeking = true; });
seek.addEventListener("change", () => {
  if (audio.duration) audio.currentTime = (seek.value / 1000) * audio.duration;
  seeking = false;
});

const volume = $("#volume");
audio.volume = volume.value / 100;
volume.addEventListener("input", () => { audio.volume = volume.value / 100; });

/* ==================================================================
   WAVEFORM-VISUALIZER
   Pulsierende Wellenlinien die mit der Musik aufsteigen, ausfaden und
   zum Boden zurückfallen. Ambient-Farbwechsel. Drei Schichten für Tiefe.
   ================================================================== */
const wave = (() => {
  const canvas = $("#waveform");
  const ctx = canvas.getContext("2d");
  const POINTS = 80;
  const LAYERS = 3;
  let analyser = null;
  let dataArr = null;
  let audioCtx = null;
  let rafId = null;
  let smoothed = new Array(POINTS).fill(0);
  let energy = 0;             // Gesamt-Energie (0..1) → steuert globale Sichtbarkeit

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = canvas.parentElement.getBoundingClientRect();
    canvas.width = r.width * dpr; canvas.height = r.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);

  function ensureAnalyser() {
    if (analyser) return true;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      audioCtx = new AC();
      const src = audioCtx.createMediaElementSource(audio);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.65;
      src.connect(analyser);
      analyser.connect(audioCtx.destination);
      dataArr = new Uint8Array(analyser.frequencyBinCount);
      return true;
    } catch (e) { analyser = null; return false; }
  }

  // Ambient-Farbpaletten (wechseln langsam)
  const palettes = [
    [228,37,43],   // Riot-Rot
    [120,40,200],  // Violett
    [0,180,160],   // Türkis
    [220,120,20],  // Amber
    [40,100,220],  // Blau
    [200,50,120],  // Pink
  ];
  function ambientRGB(layerOffset) {
    const cycle = 16000;
    const t = ((performance.now() + layerOffset * 5000) % (cycle * palettes.length)) / cycle;
    const idx = Math.floor(t) % palettes.length;
    const next = (idx + 1) % palettes.length;
    const f = t - Math.floor(t);
    const e = f * f * (3 - 2 * f);   // smoothstep
    return palettes[idx].map((v, i) => Math.round(v + (palettes[next][i] - v) * e));
  }

  function drawWave(values, layer, globalAlpha) {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    const [cr, cg, cb] = ambientRGB(layer);

    const phase = layer * 1.1 + performance.now() / (2800 + layer * 900);
    const layerScale = [1.0, 0.7, 0.45][layer] || 0.5;

    ctx.beginPath();
    ctx.moveTo(0, h);
    let prevY = h;
    for (let i = 0; i <= POINTS; i++) {
      const x = (i / POINTS) * w;
      const v = values[Math.min(i, POINTS - 1)] || 0;
      // Sinuswelle nur leicht überlagert — das Hauptsignal kommt von der Musik
      const ripple = Math.sin(phase + i * 0.18) * 0.04 * v;
      const amp = v * layerScale + ripple;
      const y = h - amp * h * 0.85;
      if (i === 0) { ctx.lineTo(x, y); }
      else {
        const prevX = ((i - 1) / POINTS) * w;
        const cpx = (prevX + x) / 2;
        ctx.bezierCurveTo(cpx, prevY, cpx, y, x, y);
      }
      prevY = y;
    }
    ctx.lineTo(w, h);
    ctx.closePath();

    // Farbe + Opazität hängt an globalAlpha (Energie)
    const layerAlpha = [0.6, 0.35, 0.18][layer] || 0.3;
    const alpha = globalAlpha * layerAlpha;
    const grad = ctx.createLinearGradient(0, h, 0, h * 0.2);
    grad.addColorStop(0, `rgba(${cr},${cg},${cb},${(alpha * 0.9).toFixed(3)})`);
    grad.addColorStop(0.6, `rgba(${cr},${cg},${cb},${(alpha * 0.5).toFixed(3)})`);
    grad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
    ctx.fillStyle = grad;
    ctx.fill();
  }

  function tick() {
    rafId = requestAnimationFrame(tick);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    if (!w || !h) return;

    const target = new Array(POINTS).fill(0);
    let rawEnergy = 0;

    if (analyser && !audio.paused) {
      analyser.getByteFrequencyData(dataArr);
      const usable = Math.floor(dataArr.length * 0.82);
      const step = usable / POINTS;
      for (let i = 0; i < POINTS; i++) {
        const start = Math.floor(i * step);
        const end = Math.max(start + 1, Math.floor((i + 1) * step));
        let sum = 0;
        for (let j = start; j < end; j++) sum += dataArr[j];
        target[i] = (sum / (end - start)) / 255;
        rawEnergy += target[i];
      }
      rawEnergy /= POINTS;
    } else if (!audio.paused) {
      // Fallback
      const t = performance.now() / 500;
      for (let i = 0; i < POINTS; i++) {
        target[i] = 0.18 + 0.15 * Math.sin(t + i * 0.22);
        rawEnergy += target[i];
      }
      rawEnergy /= POINTS;
    }

    // Werte glätten: schnell hoch (Attack), schnell zurückfallen (Gravity)
    for (let i = 0; i < POINTS; i++) {
      if (target[i] > smoothed[i]) {
        smoothed[i] += (target[i] - smoothed[i]) * 0.55;   // schneller Attack
      } else {
        smoothed[i] *= 0.88;                                 // Gravity: fällt zum Boden
        if (smoothed[i] < 0.005) smoothed[i] = 0;
      }
    }

    // Globale Energie (steuert Opazität) — schnell hoch, sanft ausfaden
    if (rawEnergy > energy) energy += (rawEnergy - energy) * 0.5;
    else energy *= 0.92;
    if (energy < 0.01) energy = 0;

    // Schichten zeichnen (hinten → vorn), Opazität = Energie
    const alpha = Math.min(1, energy * 2.5);
    for (let layer = LAYERS - 1; layer >= 0; layer--) {
      drawWave(smoothed, layer, alpha);
    }
  }

  return {
    start() {
      ensureAnalyser();
      if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
      resize();
      canvas.classList.add("active");
      if (!rafId) tick();
    },
    stop() {
      canvas.classList.remove("active");
      // Auslauf-Animation: Wellen fallen sanft zum Boden
      let fadeFrames = 0;
      function fadeOut() {
        if (fadeFrames++ > 40) {
          cancelAnimationFrame(rafId); rafId = null;
          ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
          smoothed = smoothed.map(() => 0); energy = 0;
          return;
        }
        for (let i = 0; i < POINTS; i++) { smoothed[i] *= 0.85; if (smoothed[i] < 0.005) smoothed[i] = 0; }
        energy *= 0.88;
        const w2 = canvas.clientWidth, h2 = canvas.clientHeight;
        ctx.clearRect(0, 0, w2, h2);
        const alpha = Math.min(1, energy * 2.5);
        for (let layer = LAYERS - 1; layer >= 0; layer--) drawWave(smoothed, layer, alpha);
        rafId = requestAnimationFrame(fadeOut);
      }
      if (rafId) { cancelAnimationFrame(rafId); }
      fadeOut();
    },
  };
})();

audio.addEventListener("play", () => wave.start());
audio.addEventListener("pause", () => wave.stop());
audio.addEventListener("ended", () => wave.stop());

/* ==================================================================
   VIEWS
   ================================================================== */
const view = $("#view");

function artTile(extraClass, seed, label, imgUrl) {
  const tile = el("div", { class: extraClass, style: `background:${colorOf(seed)}` });
  if (imgUrl) tile.appendChild(el("img", { class: "tile-img", src: imgUrl, alt: "" }));
  else tile.appendChild(document.createTextNode(label));
  return tile;
}

function trackRow(track, idx, queue) {
  const row = el("div", { class: "track", "data-track-id": track.id, onclick: () => player.setQueue(queue, idx) },
    el("div", { class: "track-idx" },
      el("span", { class: "num" }, String(idx + 1)),
      el("span", { class: "play-ico" }, "▶")),
    el("div", {},
      el("div", { class: "track-title" }, track.title),
      el("div", { class: "track-sub" },
        `${track.artistName} · ${track.releaseTitle}${track.genre ? " · " + track.genre : ""}`)),
    el("div", { class: "track-dur" }, fmtTime(track.duration)));
  return row;
}

function genreTags(genres) {
  const wrap = el("div", { class: "tags" });
  (genres || []).slice(0, 3).forEach((g) => wrap.appendChild(el("span", { class: "tag" }, g)));
  if ((genres || []).length > 3)
    wrap.appendChild(el("span", { class: "tag" }, `+${genres.length - 3}`));
  return wrap;
}

/* ---- Home ---- */
async function renderHome() {
  const [artists] = await Promise.all([api.artists()]);
  view.innerHTML = "";

  const hero = el("div", { class: "hero" },
    el("h1", {}, state.platform.name),
    el("p", {}, state.platform.tagline));
  // Plattform-Spenden-Button (nur wenn der Admin eine PayPal-Adresse hinterlegt hat).
  if (state.platform.donateUrl) {
    hero.appendChild(el("button", { class: "hero-donate-btn",
      title: "Hilf mit, Riot Music werbefrei und unabhängig zu halten",
      onclick: () => { trackDonateClick(""); window.open(state.platform.donateUrl, "_blank", "noopener"); } },
      "♥ Plattform unterstützen"));
  }
  view.appendChild(hero);

  view.appendChild(el("h2", { class: "section-title" }, "Künstler:innen",
    el("span", { class: "count" }, `${artists.length}`)));
  view.appendChild(artistGrid(artists));
}

function artistGrid(artists) {
  const grid = el("div", { class: "grid" });
  for (const a of artists) {
    grid.appendChild(el("div", { class: "card", onclick: () => (location.hash = `#/artist/${a.id}`) },
      artTile("card-art", a.id, initials(a.name), a.image),
      el("div", { class: "card-title" }, a.name),
      el("div", { class: "card-sub" }, `${a.releaseCount} Release(s) · ${a.trackCount} Songs`),
      genreTags(a.genres)));
  }
  return grid;
}

/* ---- Katalog (optional nach Genre gefiltert) ---- */
async function renderCatalog(genre) {
  const artists = await api.artists(genre);
  view.innerHTML = "";
  view.appendChild(el("h2", { class: "section-title" },
    genre ? `Genre: ${genre}` : "Katalog",
    el("span", { class: "count" }, `${artists.length} Künstler:innen`)));
  if (!artists.length) {
    view.appendChild(emptyState("Keine Künstler:innen in diesem Genre."));
    return;
  }
  view.appendChild(artistGrid(artists));
}

/* Plattform-Metadaten für die öffentliche Anzeige: key -> [Icon, Label] */
const SOCIAL_META = {
  website:    ["🌐", "Website"],
  instagram:  ["📷", "Instagram"],
  facebook:   ["📘", "Facebook"],
  x:          ["𝕏", "X"],
  tiktok:     ["🎵", "TikTok"],
  youtube:    ["▶️", "YouTube"],
  bandcamp:   ["🅑", "Bandcamp"],
  soundcloud: ["☁️", "SoundCloud"],
  spotify:    ["🎧", "Spotify"],
  mastodon:   ["🐘", "Mastodon"],
};
const SOCIAL_ORDER = ["website", "instagram", "facebook", "x", "tiktok",
                      "youtube", "bandcamp", "soundcloud", "spotify", "mastodon"];

function socialLinks(social) {
  const wrap = el("div", { class: "social-links" });
  if (!social) return wrap;
  for (const key of SOCIAL_ORDER) {
    const url = social[key];
    if (!url) continue;
    const [icon, label] = SOCIAL_META[key] || ["🔗", key];
    wrap.appendChild(el("a", {
      class: "social-link", href: url, target: "_blank", rel: "noopener noreferrer",
      title: label, "aria-label": label,
    }, el("span", { class: "social-ico" }, icon)));
  }
  return wrap;
}

const REPORT_REASONS = [
  "Urheberrechtsverletzung",
  "Pornografische / sexuelle Inhalte",
  "Gewalt / Verherrlichung",
  "Hassrede / Diskriminierung",
  "Spam / Betrug",
  "Sonstiges",
];

function reportButton(artist) {
  return el("button", { class: "report-btn", title: "Dieses Profil melden",
    onclick: () => showReportDialog(artist) }, "⚠ Melden");
}

function showReportDialog(artist) {
  const overlay = el("div", { class: "modal-overlay" });
  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });

  const reasonSel = el("select", { class: "report-reason" },
    ...REPORT_REASONS.map((r) => el("option", { value: r }, r)));
  const detailsInp = el("textarea", { class: "report-details", rows: 4, maxlength: 1000,
    placeholder: "Optional: kurze Begründung (was genau ist das Problem?)" });
  const status = el("div", { class: "contact-status" });
  // Honeypot
  const hp = el("input", { type: "text", name: "website", tabindex: "-1",
    autocomplete: "off", style: "position:absolute;left:-10000px;width:1px;height:1px;opacity:0" });

  const submit = el("button", { class: "primary-btn", onclick: async () => {
    submit.disabled = true;
    status.className = "contact-status";
    status.textContent = "Wird gesendet …";
    try {
      const fd = new FormData();
      fd.set("artistId", artist.id);
      fd.set("reason", reasonSel.value);
      fd.set("details", detailsInp.value);
      fd.set("website", hp.value);
      const res = await fetch("/api/report", { method: "POST", body: fd });
      if (!res.ok) {
        let d = `Fehler ${res.status}`;
        try { d = (await res.json()).detail || d; } catch {}
        throw new Error(d);
      }
      status.className = "contact-status ok";
      status.textContent = "✓ Danke! Deine Meldung wurde übermittelt und wird geprüft.";
      submit.style.display = "none";
      setTimeout(close, 2200);
    } catch (err) {
      status.className = "contact-status error";
      status.textContent = "✗ " + err.message;
      submit.disabled = false;
    }
  } }, "Meldung senden");

  overlay.appendChild(el("div", { class: "modal-box" },
    el("h3", {}, `Profil melden: ${artist.name}`),
    el("p", { class: "image-hint" },
      "Hilf mit, die Plattform sauber zu halten. Wir prüfen jede Meldung und " +
      "entfernen rechtswidrige oder regelwidrige Inhalte."),
    el("label", { class: "report-label" }, "Grund"),
    reasonSel,
    el("label", { class: "report-label" }, "Begründung (optional)"),
    detailsInp, hp,
    el("div", { class: "btn-row" }, submit,
      el("button", { class: "ghost-btn", onclick: close }, "Abbrechen")),
    status));
  document.body.appendChild(overlay);
}

function shareButton(artist) {
  const url = `${location.origin}/#/artist/${artist.id}`;
  return el("button", { class: "share-btn", title: "Profil teilen",
    onclick: async () => {
      const shareData = { title: `${artist.name} – Riot Music`,
                          text: `Hör dir ${artist.name} auf Riot Music an:`, url };
      if (navigator.share) {
        try { await navigator.share(shareData); } catch { /* abgebrochen */ }
      } else {
        try {
          await navigator.clipboard.writeText(url);
          toast("Link kopiert — jetzt teilen! ✊");
        } catch {
          window.prompt("Link zum Teilen:", url);
        }
      }
    } }, "↗ Teilen");
}

/* ---- Künstlerprofil ---- */
async function renderArtist(id) {
  let artist;
  try { artist = await api.artist(id); }
  catch { view.innerHTML = ""; view.appendChild(emptyState("Künstler:in nicht gefunden.")); return; }

  // alle Tracks der/des Künstler:in als eine durchgehende Warteschlange
  const allTracks = artist.releases.flatMap((r) => r.tracks);

  // Spenden-Button einblenden, sofern PayPal hinterlegt ist.
  showDonateButton(artist);

  view.innerHTML = "";
  const head = el("div", { class: "artist-head" });
  if (artist.banner) head.style.backgroundImage = `url(${artist.banner})`;
  head.appendChild(artTile("artist-avatar", artist.id, initials(artist.name), artist.image));
  head.appendChild(el("div", { class: "artist-head-info" },
    el("h1", {}, artist.name),
    el("div", { class: "meta" },
      genreTags(artist.genres),
      el("span", {}, artist.location || ""),
      el("span", {}, `${allTracks.length} Songs`)),
    el("div", { class: "artist-actions" },
      shareButton(artist),
      socialLinks(artist.social),
      reportButton(artist))));
  view.appendChild(head);

  view.appendChild(el("p", { class: "artist-bio" }, artist.bio));

  // Top 10 meistgespielte Songs
  if (artist.topTracks && artist.topTracks.length > 0) {
    const topGrid = el("div", { class: "top-tracks-grid" });
    topGrid.appendChild(el("h3", {}, "🔥 Beliebteste Songs"));
    const grid = el("div", { class: "tracks-grid" });
    artist.topTracks.forEach((track) => {
      const card = el("div", { class: "track-card" });
      const cover = el("div", { class: "track-cover", style: `background:${colorOf(track.releaseId)}` });
      if (track.coverThumb || track.cover) {
        cover.appendChild(el("img", { src: track.coverThumb || track.cover, alt: track.title, class: "tile-img" }));
      } else {
        cover.appendChild(document.createTextNode(initials(track.releaseTitle)));
      }
      const playBtn = el("button", { class: "play-overlay",
        onclick: () => player.setQueue(allTracks, allTracks.findIndex((t) => t.id === track.id)) },
        "▶");
      cover.appendChild(playBtn);
      card.appendChild(cover);
      card.appendChild(el("div", { class: "track-info" },
        el("div", { class: "track-title" }, track.title),
        el("div", { class: "track-artist" }, track.artistName),
        el("div", { class: "track-release" }, track.releaseTitle)));
      grid.appendChild(card);
    });
    topGrid.appendChild(grid);
    view.appendChild(topGrid);
  }

  if (artist.videoUrls && artist.videoUrls.length > 0) {
    const grid = el("div", { class: "artist-videos-grid" });
    artist.videoUrls.forEach((url) => {
      grid.appendChild(el("iframe", {
        src: url,
        allow: "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
        allowfullscreen: true,
        title: `Video von ${artist.name}`,
        class: "artist-video-iframe",
      }));
    });
    view.appendChild(grid);
  }

  artist.releases.forEach((release) => {
    const block = el("div", { class: "release" });
    const offset = allTracks.findIndex((t) => t.id === release.tracks[0].id);
    block.appendChild(el("div", { class: "release-head" },
      artTile("release-cover", release.id, initials(release.title), release.coverThumb || release.cover),
      el("div", { class: "release-info" },
        el("h3", {}, release.title),
        el("div", { class: "sub" },
          `${release.type}${release.genre ? " · " + release.genre : ""} · ${release.year} · ${release.tracks.length} Songs`)),
      el("button", { class: "play-all", onclick: () => player.setQueue(allTracks, offset) }, "▶ Alle abspielen")));

    const list = el("div", { class: "tracklist" });
    release.tracks.forEach((track) => {
      const globalIdx = allTracks.findIndex((t) => t.id === track.id);
      list.appendChild(trackRow(track, globalIdx, allTracks));
    });
    block.appendChild(list);
    view.appendChild(block);
  });
  // Indizes in den Rows zeigen die Albumposition statt der globalen – kosmetisch korrigieren:
  fixTrackNumbers(artist);
  highlightPlaying();
}

function fixTrackNumbers(artist) {
  let perRelease = [];
  artist.releases.forEach((r) => r.tracks.forEach((t, i) => perRelease.push([t.id, i + 1])));
  const map = new Map(perRelease);
  document.querySelectorAll(".track").forEach((row) => {
    const num = $(".num", row);
    if (num && map.has(row.dataset.trackId)) num.textContent = String(map.get(row.dataset.trackId));
  });
}

/* ---- Suche ---- */
async function renderSearch(q, genre) {
  const data = await api.search(q, genre);
  $("#search-input").value = q || "";
  $("#search-genre").value = genre || "";
  view.innerHTML = "";

  const total = data.artists.length + data.releases.length + data.tracks.length;
  view.appendChild(el("h2", { class: "section-title" },
    q ? `Suche: „${q}"` : "Alle Ergebnisse",
    el("span", { class: "count" }, `${total} Treffer${genre ? " · " + genre : ""}`)));

  if (!total) { view.appendChild(emptyState("Nichts gefunden. Anderen Begriff probieren?")); return; }

  if (data.artists.length) {
    view.appendChild(el("h3", { class: "section-title" }, "Künstler:innen"));
    view.appendChild(artistGrid(data.artists.map((a) => ({ ...a, releaseCount: "—", trackCount: "—" }))));
  }

  if (data.tracks.length) {
    const sec = el("div", { class: "search-section" });
    sec.appendChild(el("h3", { class: "section-title" }, "Songs"));
    const list = el("div", { class: "tracklist" });
    data.tracks.forEach((t, i) => list.appendChild(trackRow(t, i, data.tracks)));
    sec.appendChild(list);
    view.appendChild(sec);
  }

  if (data.releases.length) {
    const sec = el("div", { class: "search-section" });
    sec.appendChild(el("h3", { class: "section-title" }, "Releases"));
    const list = el("div", { class: "row-list" });
    data.releases.forEach((r) => {
      list.appendChild(el("div", { class: "row", onclick: () => (location.hash = `#/artist/${r.artistId}`) },
        artTile("row-art", r.id, initials(r.title), r.coverThumb || r.cover),
        el("div", { class: "row-main" },
          el("div", { class: "t" }, r.title),
          el("div", { class: "s" },
            `${r.type} · ${r.artistName} · ${r.year}${r.genre ? " · " + r.genre : ""}`))));
    });
    sec.appendChild(list);
    view.appendChild(sec);
  }
  highlightPlaying();
}

/* ---- Manifest ---- */
function renderManifest() {
  view.innerHTML = "";
  const wrap = el("div", { class: "manifest" });
  wrap.appendChild(el("h1", {}, "Manifest"));
  wrap.appendChild(el("p", { class: "lead" }, state.platform.tagline));
  // Manifest-Text kann Absätze enthalten (\n\n)
  (state.platform.manifesto || "").split(/\n\n+/).forEach((para) => {
    if (para.trim()) wrap.appendChild(el("p", {}, para.trim()));
  });
  wrap.appendChild(el("p", { class: "manifest-foot" },
    "Riot Music ist ein Prototyp. Diese Werte stehen im Code, nicht nur im Marketing."));
  view.appendChild(wrap);
}

function emptyState(msg) {
  return el("div", { class: "empty" }, el("div", { class: "big" }, "🔍"), el("div", {}, msg));
}

/* ==================================================================
   KONTAKTFORMULAR (öffentlich, mit Anti-Bot)
   ================================================================== */
async function renderContact() {
  view.innerHTML = "";
  const wrap = el("div", { class: "contact-page" });
  wrap.appendChild(el("h1", {}, "Kontakt"));
  wrap.appendChild(el("p", { class: "lead" },
    "Du hast eine Frage, einen Hinweis oder einen Vorschlag? " +
    "Schick uns gerne eine Nachricht – wir lesen mit."));

  const form = el("form", { class: "contact-form" });

  form.appendChild(el("div", { class: "field" },
    el("label", {}, "Dein Name"),
    el("input", { name: "name", type: "text", required: true, maxlength: 120,
      autocomplete: "name", placeholder: "Vor- und Nachname" })));

  form.appendChild(el("div", { class: "field" },
    el("label", {}, "Deine E-Mail-Adresse"),
    el("input", { name: "email", type: "email", required: true, maxlength: 200,
      autocomplete: "email", placeholder: "du@beispiel.de" })));

  form.appendChild(el("div", { class: "field" },
    el("label", {}, "Betreff"),
    el("input", { name: "subject", type: "text", required: true, maxlength: 200,
      placeholder: "Worum geht es?" })));

  const bodyInput = el("textarea", {
    name: "body", required: true, minlength: 10, maxlength: 5000,
    rows: 8, placeholder: "Deine Nachricht (mind. 10 Zeichen) …",
  });
  const counter = el("div", { class: "char-counter" }, "0 / 5000");
  bodyInput.addEventListener("input", () => {
    counter.textContent = `${bodyInput.value.length} / 5000`;
  });
  form.appendChild(el("div", { class: "field" },
    el("label", {}, "Nachricht"), bodyInput, counter));

  // Honeypot – für Menschen unsichtbar, Bots füllen es oft aus.
  form.appendChild(el("div", {
    "aria-hidden": "true",
    style: "position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none",
  },
    el("label", {}, "Website (bitte leer lassen)"),
    el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off" })));

  // Mathe-Captcha
  let captchaState = null;
  const captchaQ = el("div", { class: "captcha-q" }, "lädt …");
  const captchaInput = el("input", { name: "captchaAnswer", required: true,
    inputmode: "numeric", autocomplete: "off", placeholder: "Antwort" });
  const captchaIdInput = el("input", { type: "hidden", name: "captchaId" });
  const reloadBtn = el("button", { type: "button", class: "ghost-btn small",
    onclick: (e) => { e.preventDefault(); loadCaptcha(); } }, "↻ Neu");

  async function loadCaptcha() {
    captchaQ.textContent = "lädt …";
    try {
      captchaState = await fetch("/api/auth/captcha").then((r) => r.json());
      captchaQ.textContent = captchaState.question;
      captchaIdInput.value = captchaState.id;
      captchaInput.value = "";
    } catch {
      captchaQ.textContent = "Captcha konnte nicht geladen werden.";
    }
  }

  form.appendChild(el("div", { class: "field captcha-field" },
    el("label", {}, "Sicherheitsfrage (Anti-Spam)"),
    el("div", { class: "captcha-row" }, captchaQ, captchaInput, reloadBtn),
    captchaIdInput));

  form.appendChild(el("p", { class: "form-hint" },
    "Hinweis: Wir prüfen jede Nachricht automatisch auf Spam. " +
    "Maximal 5 Anfragen pro Stunde von derselben Adresse."));

  const submitBtn = el("button", { type: "submit", class: "primary-btn" },
    "Nachricht senden");
  const status = el("div", { class: "contact-status" });
  form.appendChild(el("div", { class: "btn-row" }, submitBtn, status));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submitBtn.disabled = true;
    status.textContent = "Wird gesendet …";
    status.className = "contact-status";
    try {
      const fd = new FormData(form);
      const res = await fetch("/api/contact", { method: "POST", body: fd });
      if (!res.ok) {
        let detail = `Fehler ${res.status}`;
        try { detail = (await res.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      status.textContent = "✓ Deine Nachricht wurde gesendet. Vielen Dank!";
      status.className = "contact-status ok";
      form.reset();
      await loadCaptcha();
      // Counter zurücksetzen
      counter.textContent = "0 / 5000";
    } catch (err) {
      status.textContent = "✗ " + err.message;
      status.className = "contact-status error";
      await loadCaptcha();   // Captcha ist verbraucht – neues laden
    } finally {
      submitBtn.disabled = false;
    }
  });

  wrap.appendChild(form);
  view.appendChild(wrap);
  loadCaptcha();
}

/* ==================================================================
   ROUTER
   ================================================================== */
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, queryStr] = raw.split("?");
  const params = new URLSearchParams(queryStr || "");
  const parts = path.split("/").filter(Boolean);
  return { parts, params };
}

async function router() {
  const { parts, params } = parseHash();
  setActiveNav(parts[0] || "home");

  // Spenden-Button standardmäßig ausblenden – renderArtist blendet ihn bei
  // hinterlegter PayPal-Adresse wieder ein.
  hideDonateButton();

  try {
    if (!parts.length) return await renderHome();
    switch (parts[0]) {
      case "catalog": return await renderCatalog(params.get("genre"));
      case "artist": return await renderArtist(parts[1]);
      case "search": return await renderSearch(params.get("q") || "", params.get("genre"));
      case "manifest": return renderManifest();
      case "kontakt": return await renderContact();
      default: return await renderHome();
    }
  } catch (err) {
    view.innerHTML = "";
    view.appendChild(emptyState("Fehler beim Laden: " + err.message));
  }
}

function setActiveNav(route) {
  document.querySelectorAll(".nav-link").forEach((l) =>
    l.classList.toggle("active", l.dataset.route === route));
}
window.addEventListener("hashchange", router);

/* ==================================================================
   SUCHLEISTE + GENRES
   ================================================================== */
$("#search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#search-input").value.trim();
  const genre = $("#search-genre").value;
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (genre) p.set("genre", genre);
  location.hash = `#/search?${p.toString()}`;
});

function buildGenres() {
  const sel = $("#search-genre");
  state.genres.forEach((g) => sel.appendChild(el("option", { value: g }, g)));
}

/* ==================================================================
   START
   ================================================================== */
(async function init() {
  try {
    [state.platform, state.genres] = await Promise.all([api.platform(), api.genres()]);
  } catch (err) {
    view.innerHTML = `<div class="empty"><div class="big">⚠️</div>Backend nicht erreichbar.<br>Läuft der Server? (${err.message})</div>`;
    return;
  }
  document.title = `${state.platform.name} — Musik gehört den Menschen`;
  buildGenres();
  router();
})();
