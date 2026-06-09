/* Riot Music — Studio (Künstler-Backend) */
"use strict";

const $ = (s, r = document) => r.querySelector(s);

const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
};

const initials = (name) => name.split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();
function colorOf(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) % 360;
  return `linear-gradient(135deg, hsl(${h} 62% 38%), hsl(${(h + 40) % 360} 64% 24%))`;
}
const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

let toastTimer;
function toast(msg, kind = "ok") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 2800);
}

async function apiSend(method, url, formData) {
  const res = await fetch(url, { method, body: formData });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}
const apiGet = (url) => fetch(url).then((r) => r.json());

/* ---------- Zustand ---------- */
const state = { artists: [], genres: [], selectedId: null, creating: false };

/* ---------- Sidebar ---------- */
function renderSidebar() {
  const list = $("#artist-list");
  list.innerHTML = "";
  state.artists.forEach((a) => {
    const av = el("div", { class: "av", style: `background:${colorOf(a.id)}` });
    if (a.imageThumb) av.appendChild(el("img", { src: a.imageThumb, alt: "" }));
    else av.textContent = initials(a.name);
    list.appendChild(el("div", {
      class: "studio-artist" + (a.id === state.selectedId && !state.creating ? " active" : ""),
      onclick: () => selectArtist(a.id),
    }, av, el("div", {},
      el("div", { class: "nm" }, a.name),
      el("div", { class: "gn" }, `${(a.genres && a.genres.join(", ")) || "kein Genre"} · ${a.trackCount} Songs`))));
  });
}

/* ---------- Bild-Feld mit Vorschau ---------- */
function imageField({ label, name, round, currentUrl, hint }) {
  const preview = el("div", { class: "image-preview" + (round ? " round" : "") });
  if (currentUrl) preview.appendChild(el("img", { src: currentUrl, alt: "" }));
  else preview.textContent = "🖼";
  const input = el("input", { type: "file", name, accept: "image/jpeg,.jpg,.jpeg" });
  input.addEventListener("change", () => {
    const f = input.files[0];
    if (!f) return;
    preview.innerHTML = "";
    preview.appendChild(el("img", { src: URL.createObjectURL(f), alt: "" }));
  });
  return el("div", { class: "field full" },
    el("label", {}, label),
    el("div", { class: "image-field" }, preview,
      el("div", {}, input, el("div", { class: "image-hint" }, hint))));
}

/* ---------- Künstler-Editor ---------- */
function genreOptions(selected) {
  const dl = el("datalist", { id: "genre-options" });
  state.genres.forEach((g) => dl.appendChild(el("option", { value: g })));
  return dl;
}

function renderEditor(artist) {
  const main = $("#studio-main");
  main.innerHTML = "";
  const isNew = !artist;

  // ----- Künstler-Stammdaten -----
  const form = el("form", { class: "panel", id: "artist-form" });
  form.appendChild(el("div", { class: "panel-head" },
    el("h2", {}, isNew ? "Neue:r Künstler:in" : artist.name),
    !isNew && el("button", { type: "button", class: "danger-btn",
      onclick: () => deleteArtist(artist) }, "Künstler:in löschen")));

  form.appendChild(el("div", { class: "form-grid" },
    el("div", { class: "field" }, el("label", {}, "Name *"),
      el("input", { name: "name", required: true, value: isNew ? "" : artist.name })),
    el("div", { class: "field" }, el("label", {}, "Ort"),
      el("input", { name: "location", value: isNew ? "" : (artist.location || "") })),
    el("div", { class: "field full" }, el("label", {}, "Bio"),
      el("textarea", { name: "bio" }, isNew ? "" : (artist.bio || ""))),
    imageField({ label: "Künstlerbild (nur JPEG, max. 5 MB)", name: "image", round: true,
      currentUrl: isNew ? null : artist.image,
      hint: "Wird automatisch quadratisch zugeschnitten & skaliert." }),
    imageField({ label: "Banner (nur JPEG, Breitformat, max. 5 MB)", name: "banner", round: false,
      currentUrl: isNew ? null : artist.banner,
      hint: "Wird auf 1400×400 zugeschnitten. Genre wird pro Release/Song gesetzt." })));

  form.appendChild(el("div", { class: "btn-row" },
    el("button", { type: "submit", class: "primary-btn" }, isNew ? "Anlegen" : "Speichern")));

  form.addEventListener("submit", (e) => { e.preventDefault(); saveArtist(form, artist); });
  main.appendChild(form);

  // ----- Releases (nur bei bestehendem Künstler) -----
  if (!isNew) {
    main.appendChild(renderReleasesPanel(artist));
  }
}

function renderReleasesPanel(artist) {
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h3", {}, `Releases (${artist.releases.length})`));

  artist.releases.forEach((rel) => panel.appendChild(renderReleaseCard(artist, rel)));

  // Neues Release anlegen
  const f = el("form", { class: "release-card" });
  f.appendChild(el("div", { class: "inline-form" },
    el("div", { class: "field", style: "flex:2" }, el("label", {}, "Titel *"),
      el("input", { name: "title", required: true, placeholder: "Album-/EP-/Single-Titel" })),
    el("div", { class: "field" }, el("label", {}, "Typ"),
      el("select", { name: "type" },
        el("option", {}, "Album"), el("option", {}, "EP"),
        el("option", { selected: true }, "Single"))),
    el("div", { class: "field" }, el("label", {}, "Jahr"),
      el("input", { name: "year", type: "number", value: new Date().getFullYear(),
        min: 1900, max: 2100 })),
    el("div", { class: "field" }, el("label", {}, "Genre"),
      el("input", { name: "genre", list: "genre-options", placeholder: "frei wählbar" }), genreOptions()),
    el("button", { type: "submit", class: "primary-btn" }, "+ Release")));
  f.appendChild(imageField({ label: "Cover (nur JPEG, optional, max. 5 MB)", name: "cover",
    hint: "Quadratisch zugeschnitten & skaliert." }));
  f.addEventListener("submit", (e) => { e.preventDefault(); addRelease(f, artist); });
  panel.appendChild(f);
  return panel;
}

function renderReleaseCard(artist, rel) {
  const cover = el("div", { class: "release-cover-sm", style: `background:${colorOf(rel.id)}` });
  if (rel.coverThumb) cover.appendChild(el("img", { src: rel.coverThumb, alt: "" }));
  else cover.textContent = initials(rel.title);

  const card = el("div", { class: "release-card" });
  card.appendChild(el("div", { class: "release-card-head" }, cover,
    el("div", { class: "info" },
      el("div", { class: "t" }, rel.title),
      el("div", { class: "s" }, `${rel.type}${rel.genre ? " · " + rel.genre : ""} · ${rel.year} · ${rel.tracks.length} Songs`)),
    el("button", { class: "danger-btn", onclick: () => deleteRelease(artist, rel) }, "Löschen")));

  rel.tracks.forEach((t, i) => {
    card.appendChild(el("div", { class: "studio-track" },
      el("span", { class: "idx" }, String(i + 1)),
      el("span", {}, t.title + (t.trackGenre ? `  ·  ${t.trackGenre}` : "")),
      el("span", { class: "dur" }, t.duration ? fmtTime(t.duration) : "–"),
      el("button", { class: "del", title: "Track löschen",
        onclick: () => deleteTrack(artist, t) }, "✕")));
  });

  // Track-Upload
  const tf = el("form", { class: "inline-form" });
  tf.appendChild(el("div", { class: "field", style: "flex:2" }, el("label", {}, "Songtitel *"),
    el("input", { name: "title", required: true, placeholder: "Songtitel" })));
  tf.appendChild(el("div", { class: "field" }, el("label", {}, "Genre (optional)"),
    el("input", { name: "genre", list: "genre-options", placeholder: "erbt vom Release" }), genreOptions()));
  tf.appendChild(el("div", { class: "field", style: "flex:2" }, el("label", {}, "Audiodatei (MP3) *"),
    el("input", { name: "audio", type: "file", required: true,
      accept: "audio/mpeg,.mp3" })));
  tf.appendChild(el("button", { type: "submit", class: "ghost-btn" }, "+ Song"));
  tf.addEventListener("submit", (e) => { e.preventDefault(); addTrack(tf, artist, rel); });
  card.appendChild(tf);
  return card;
}

/* ---------- Aktionen ---------- */
async function saveArtist(form, artist) {
  const fd = new FormData(form);
  // leere Datei-Inputs nicht mitschicken
  if (!fd.get("image")?.size) fd.delete("image");
  if (!fd.get("banner")?.size) fd.delete("banner");
  try {
    const btn = $("button[type=submit]", form); btn.disabled = true;
    let saved;
    if (artist) saved = await apiSend("PUT", `/api/manage/artists/${artist.id}`, fd);
    else saved = await apiSend("POST", "/api/manage/artists", fd);
    toast(artist ? "Gespeichert." : "Künstler:in angelegt.", "ok");
    await reload(saved.id);
  } catch (err) {
    toast("Fehler: " + err.message, "error");
    const btn = $("button[type=submit]", form); if (btn) btn.disabled = false;
  }
}

async function addRelease(form, artist) {
  const fd = new FormData(form);
  if (!fd.get("cover")?.size) fd.delete("cover");
  try {
    await apiSend("POST", `/api/manage/artists/${artist.id}/releases`, fd);
    toast("Release angelegt.", "ok");
    await reload(artist.id);
  } catch (err) { toast("Fehler: " + err.message, "error"); }
}

async function addTrack(form, artist, rel) {
  const fd = new FormData(form);
  try {
    const btn = $("button[type=submit]", form); btn.disabled = true;
    btn.textContent = "Lädt…";
    await apiSend("POST", `/api/manage/releases/${rel.id}/tracks`, fd);
    toast("Song hinzugefügt.", "ok");
    await reload(artist.id);
  } catch (err) { toast("Fehler: " + err.message, "error"); }
}

async function deleteArtist(artist) {
  if (!confirm(`„${artist.name}" und alle Releases/Songs wirklich löschen?`)) return;
  try {
    await apiSend("DELETE", `/api/manage/artists/${artist.id}`);
    toast("Gelöscht.", "ok");
    state.selectedId = null;
    await reload(null);
  } catch (err) { toast("Fehler: " + err.message, "error"); }
}

async function deleteRelease(artist, rel) {
  if (!confirm(`Release „${rel.title}" löschen?`)) return;
  try {
    await apiSend("DELETE", `/api/manage/releases/${rel.id}`);
    toast("Release gelöscht.", "ok");
    await reload(artist.id);
  } catch (err) { toast("Fehler: " + err.message, "error"); }
}

async function deleteTrack(artist, track) {
  try {
    await apiSend("DELETE", `/api/manage/tracks/${track.id}`);
    toast("Song gelöscht.", "ok");
    await reload(artist.id);
  } catch (err) { toast("Fehler: " + err.message, "error"); }
}

/* ---------- Navigation / Laden ---------- */
function selectArtist(id) {
  state.selectedId = id;
  state.creating = false;
  const artist = state.artists.find((a) => a.id === id);
  renderSidebar();
  renderEditor(artist);
}

function newArtist() {
  state.creating = true;
  state.selectedId = null;
  renderSidebar();
  renderEditor(null);
}

async function reload(selectId) {
  state.artists = await apiGet("/api/manage/artists");
  state.genres = await apiGet("/api/genres");
  if (selectId) {
    state.selectedId = selectId;
    state.creating = false;
  }
  renderSidebar();
  const sel = state.artists.find((a) => a.id === state.selectedId);
  if (sel) renderEditor(sel);
  else if (!state.creating) {
    $("#studio-main").innerHTML = "";
    $("#studio-main").appendChild(el("div", { class: "studio-placeholder" },
      el("div", { class: "big" }, "🎙️"),
      el("p", { html: "Wähle links eine:n Künstler:in aus<br>oder lege eine:n neue:n an." })));
  }
}

$("#btn-new-artist").addEventListener("click", newArtist);

/* ---------- Admin-Auth ---------- */
function renderAdminLogin(mode, loggedInAs) {
  // mode: "login" | "bootstrap" (erster Admin anlegen)
  const layout = document.querySelector(".studio-layout");
  layout.innerHTML = "";
  const card = el("div", { class: "auth-card", style: "margin:8vh auto 0" });
  card.appendChild(el("h1", {}, mode === "bootstrap" ? "Admin-Account anlegen" : "Admin-Login"));
  card.appendChild(el("p", { class: "auth-sub" },
    mode === "bootstrap"
      ? "Noch kein Admin vorhanden. Lege jetzt den ersten an."
      : "Nur für berechtigte Administrator:innen."));

  if (loggedInAs) {
    const hint = el("div", { class: "auth-loggedin",
      style: "margin:0 0 16px;padding:10px 12px;background:var(--bg-elev);border:1px solid var(--border);border-radius:8px;font-size:.92rem;color:var(--text-dim);display:flex;align-items:center;gap:10px;flex-wrap:wrap" },
      el("span", {}, `Eingeloggt als ${loggedInAs} (kein Admin).`),
      el("button", { type: "button", class: "ghost-btn",
        onclick: async () => {
          try {
            await apiSend("POST", "/api/auth/logout", new FormData());
            location.reload();
          } catch (err) { toast("Logout fehlgeschlagen: " + err.message, "error"); }
        } }, "Abmelden"));
    card.appendChild(hint);
  }

  const form = el("form", { class: "auth-form" });
  form.appendChild(el("div", { class: "field" }, el("label", {}, "E-Mail"),
    el("input", { name: "email", type: "email", required: true, autocomplete: "email" })));
  form.appendChild(el("div", { class: "field" }, el("label", {}, "Passwort"),
    el("input", { name: "password", type: "password", required: true, minlength: 8 })));

  let reloadCaptcha = null;
  if (mode === "bootstrap") {
    // Honeypot: für Menschen unsichtbar, Bots füllen es trotzdem aus.
    form.appendChild(el("div", {
      "aria-hidden": "true",
      style: "position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none",
    },
      el("label", {}, "Website (bitte leer lassen)"),
      el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off" })));
    const captchaQ = el("div", { class: "captcha-q", style: "padding:8px 0;color:var(--text-dim)" }, "lädt …");
    const captchaInput = el("input", { name: "captchaAnswer", required: true,
      inputmode: "numeric", autocomplete: "off", placeholder: "Antwort" });
    const captchaIdInput = el("input", { type: "hidden", name: "captchaId" });
    reloadCaptcha = async () => {
      try {
        const c = await fetch("/api/auth/captcha").then(r => r.json());
        captchaQ.textContent = c.question;
        captchaIdInput.value = c.id;
        captchaInput.value = "";
      } catch {
        captchaQ.textContent = "Captcha konnte nicht geladen werden.";
      }
    };
    form.appendChild(el("div", { class: "field" },
      el("label", {}, "Anti-Bot-Frage"), captchaQ, captchaInput, captchaIdInput));
    reloadCaptcha();
  }

  form.appendChild(el("button", { type: "submit", class: "primary-btn full" },
    mode === "bootstrap" ? "Admin-Account erstellen" : "Anmelden"));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const url = mode === "bootstrap" ? "/api/auth/admin-register" : "/api/auth/login";
    try {
      const btn = $("button[type=submit]", form); btn.disabled = true;
      const data = await apiSend("POST", url, fd);
      if (data.role !== "admin" && mode !== "bootstrap") {
        toast("Dieses Konto hat keinen Admin-Zugang.", "error");
        btn.disabled = false;
        return;
      }
      toast(mode === "bootstrap" ? "Admin angelegt!" : "Willkommen!", "ok");
      startAdmin();
    } catch (err) {
      toast("Fehler: " + err.message, "error");
      const btn = $("button[type=submit]", form); if (btn) btn.disabled = false;
      if (reloadCaptcha) reloadCaptcha();
    }
  });

  card.appendChild(form);
  layout.appendChild(card);
}

async function startAdmin() {
  const layout = document.querySelector(".studio-layout");
  layout.innerHTML = "";
  const aside = el("aside", { class: "studio-side" });
  aside.appendChild(el("button", { class: "primary-btn full", onclick: newArtist }, "+ Neue:r Künstler:in"));
  aside.appendChild(el("button", { class: "ghost-btn full", style: "margin-top:8px",
    onclick: showOverview }, "📊 Übersicht"));
  aside.appendChild(el("button", { class: "ghost-btn full", style: "margin-top:8px",
    onclick: showPayout }, "💰 Auszahlung"));
  aside.appendChild(el("button", { class: "ghost-btn full", style: "margin-top:8px",
    onclick: downloadEmails }, "📧 E-Mails exportieren"));
  const inboxBtn = el("button", { class: "ghost-btn full", style: "margin-top:8px",
    id: "btn-inbox", onclick: showInbox }, "✉ Posteingang");
  aside.appendChild(inboxBtn);
  // Ungelesen-Badge im Hintergrund laden
  refreshInboxBadge(inboxBtn);
  const unverifiedBtn = el("button", { class: "ghost-btn full", style: "margin-top:8px",
    id: "btn-unverified", onclick: showUnverified }, "🕓 Unbestätigte Konten");
  aside.appendChild(unverifiedBtn);
  refreshUnverifiedBadge(unverifiedBtn);
  aside.appendChild(el("button", { class: "ghost-btn full", style: "margin-top:8px",
    onclick: showSettings }, "⚙ E-Mail-Einstellungen"));
  aside.appendChild(el("div", { id: "artist-list", class: "studio-artist-list" }));
  const main = el("main", { class: "studio-main", id: "studio-main" });
  main.appendChild(el("div", { class: "studio-placeholder" },
    el("div", { class: "big" }, "🛡️"),
    el("p", { html: "Admin-Verwaltung: alle Künstler:innen, Releases und Songs.<br>Wähle links eine:n aus oder lege eine:n neue:n an." })));
  layout.appendChild(aside);
  layout.appendChild(main);
  try {
    await reload(null);
  } catch (err) { toast("Fehler beim Laden: " + err.message, "error"); }
}

/* ---------- E-Mail-Export ---------- */
function downloadEmails() {
  const result = prompt("Wähle Format: CSV (Enter drücken) oder JSON (json eingeben):");
  if (result === null) return;  // Abgebrochen

  const format = result.toLowerCase().trim() === "json" ? "json" : "csv";
  const url = `/api/artists/export/emails.${format}`;

  // Download starten
  const link = document.createElement("a");
  link.href = url;
  link.download = `artist-emails.${format}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  toast(`E-Mails als ${format.toUpperCase()} exportiert.`, "ok");
}

/* ---------- Kontakt-Posteingang ---------- */
async function refreshInboxBadge(btn) {
  try {
    const data = await fetch("/api/admin/contact-messages").then(r => r.json());
    const unread = (data && data.unread) || 0;
    btn.textContent = unread > 0 ? `✉ Posteingang (${unread})` : "✉ Posteingang";
  } catch { /* still icon */ }
}

async function showInbox() {
  state.selectedId = null;
  state.creating = false;
  renderSidebar();
  const main = $("#studio-main");
  main.innerHTML = "";

  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "✉ Posteingang — Kontaktnachrichten"));
  panel.appendChild(el("p", { style: "color:var(--text-dim);margin-bottom:18px" },
    "Nachrichten von Besucher:innen über das öffentliche Kontaktformular. " +
    "Diese werden lokal gespeichert; ein automatischer E-Mail-Versand wird später ergänzt."));

  const listWrap = el("div", { class: "inbox-list" });
  panel.appendChild(listWrap);
  main.appendChild(panel);

  async function load() {
    listWrap.innerHTML = "Laden …";
    try {
      const data = await fetch("/api/admin/contact-messages").then(r => r.json());
      const messages = data.messages || [];
      listWrap.innerHTML = "";
      if (!messages.length) {
        listWrap.appendChild(el("p", { style: "color:var(--text-dim)" }, "Keine Nachrichten."));
        return;
      }
      messages.forEach((m) => listWrap.appendChild(renderInboxItem(m, load)));
      const btn = document.getElementById("btn-inbox");
      if (btn) refreshInboxBadge(btn);
    } catch (err) {
      listWrap.innerHTML = "";
      listWrap.appendChild(el("p", { style: "color:#ff6b6f" }, "Fehler: " + err.message));
    }
  }
  load();
}

function renderInboxItem(m, reload) {
  const isReport = m.type === "report";
  const card = el("div", { class: "inbox-item" + (m.read ? "" : " unread") + (isReport ? " report" : "") });
  const dateStr = new Date(m.createdAt).toLocaleString("de-DE");

  // Absenderzeile: Meldung verweist auf das gemeldete Profil, Kontakt auf E-Mail.
  const fromLine = isReport
    ? el("div", { class: "inbox-from" }, "Gemeldetes Profil: ",
        m.reportedArtistId
          ? el("a", { href: `/#/artist/${m.reportedArtistId}`, target: "_blank" },
              m.reportedArtistName || m.reportedArtistId)
          : (m.reportedArtistName || "(unbekannt)"))
    : el("div", { class: "inbox-from" }, `${m.name} `,
        el("a", { href: `mailto:${m.email}` }, `<${m.email}>`));

  const actions = el("div", { class: "inbox-actions" },
    el("button", { class: "ghost-btn small", onclick: async () => {
      await fetch(`/api/admin/contact-messages/${m.id}/read?read=${!m.read}`, { method: "POST" });
      reload();
    } }, m.read ? "als ungelesen" : "als gelesen"));
  // Antworten nur bei echten Kontaktnachrichten mit E-Mail.
  if (!isReport && m.email) {
    actions.appendChild(el("a", { class: "ghost-btn small",
      href: `mailto:${m.email}?subject=Re: ${encodeURIComponent(m.subject)}` }, "Antworten"));
  }
  // Bei Meldungen: direkter Sprung zum Bearbeiten/Löschen des gemeldeten Profils.
  if (isReport && m.reportedArtistId) {
    actions.appendChild(el("button", { class: "ghost-btn small",
      onclick: () => selectArtist(m.reportedArtistId) }, "Profil öffnen"));
  }
  actions.appendChild(el("button", { class: "danger-btn", onclick: async () => {
    if (!confirm(isReport ? "Meldung aus dem Posteingang entfernen?" : "Nachricht wirklich löschen?")) return;
    await fetch(`/api/admin/contact-messages/${m.id}`, { method: "DELETE" });
    reload();
  } }, "Löschen"));

  const head = el("div", { class: "inbox-head" },
    el("div", { class: "inbox-meta" },
      el("strong", {},
        isReport ? el("span", { class: "report-badge" }, "⚠ MELDUNG") : null,
        " " + (m.subject || "(ohne Betreff)")),
      fromLine,
      el("div", { class: "inbox-date" }, dateStr + (m.ip ? ` · IP ${m.ip}` : ""))),
    actions);

  card.appendChild(head);
  card.appendChild(el("pre", { class: "inbox-body" }, m.body));
  return card;
}

/* ---------- Unbestätigte Konten (Double-Opt-In offen) ---------- */
async function refreshUnverifiedBadge(btn) {
  try {
    const data = await fetch("/api/admin/unverified").then(r => r.json());
    const n = (data && data.count) || 0;
    btn.textContent = n > 0 ? `🕓 Unbestätigte Konten (${n})` : "🕓 Unbestätigte Konten";
  } catch { /* ignore */ }
}

async function showUnverified() {
  state.selectedId = null;
  state.creating = false;
  renderSidebar();
  const main = $("#studio-main");
  main.innerHTML = "";

  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "🕓 Unbestätigte Konten"));
  panel.appendChild(el("p", { style: "color:var(--text-dim);margin-bottom:18px" },
    "Konten, deren E-Mail-Bestätigung (Double-Opt-In) noch aussteht. Solche Profile " +
    "sind nicht öffentlich sichtbar. Du kannst sie manuell freischalten oder löschen."));

  const listWrap = el("div", { class: "inbox-list" });
  panel.appendChild(listWrap);
  main.appendChild(panel);

  async function load() {
    listWrap.innerHTML = "Laden …";
    try {
      const data = await fetch("/api/admin/unverified").then(r => r.json());
      listWrap.innerHTML = "";

      if (!data.mailEnabled) {
        listWrap.appendChild(el("p", { class: "fp-banner partial" },
          "⚠ Kein SMTP konfiguriert — neue Registrierungen werden derzeit ohne " +
          "E-Mail-Bestätigung sofort freigeschaltet."));
      }

      const items = data.unverified || [];
      if (!items.length) {
        listWrap.appendChild(el("p", { style: "color:var(--text-dim)" },
          "Keine offenen Bestätigungen. 👍"));
      } else {
        // Sammel-Aufräumen
        listWrap.appendChild(el("div", { style: "margin-bottom:14px" },
          el("button", { class: "danger-btn", onclick: async () => {
            if (!confirm("Alle unbestätigten Konten löschen, die älter als 7 Tage sind?")) return;
            const r = await fetch("/api/admin/prune-unverified", { method: "POST" }).then(r => r.json());
            toast(`${r.removed} altes Konto/Konten entfernt.`, "ok");
            load();
          } }, "🧹 Alte (>7 Tage) aufräumen")));

        items.forEach((u) => listWrap.appendChild(renderUnverifiedItem(u, load)));
      }
      const btn = document.getElementById("btn-unverified");
      if (btn) refreshUnverifiedBadge(btn);
    } catch (err) {
      listWrap.innerHTML = "";
      listWrap.appendChild(el("p", { style: "color:#ff6b6f" }, "Fehler: " + err.message));
    }
  }
  load();
}

function renderUnverifiedItem(u, reload) {
  const card = el("div", { class: "inbox-item unread" });
  const created = u.createdAt ? new Date(u.createdAt * 1000).toLocaleString("de-DE") : "?";
  card.appendChild(el("div", { class: "inbox-head" },
    el("div", { class: "inbox-meta" },
      el("strong", {}, u.artistName || "(ohne Namen)"),
      el("div", { class: "inbox-from" }, u.email),
      el("div", { class: "inbox-date" }, `Registriert: ${created} · seit ${u.ageHours} h offen`)),
    el("div", { class: "inbox-actions" },
      el("button", { class: "ghost-btn small", onclick: async () => {
        await fetch(`/api/admin/unverified/${encodeURIComponent(u.email)}/verify`,
                    { method: "POST" });
        toast("Konto freigeschaltet.", "ok");
        reload();
      } }, "✓ Freischalten"),
      el("button", { class: "danger-btn", onclick: async () => {
        if (!confirm(`Konto „${u.email}" und Profil endgültig löschen?`)) return;
        await fetch(`/api/admin/unverified/${encodeURIComponent(u.email)}`,
                    { method: "DELETE" });
        toast("Konto gelöscht.", "ok");
        reload();
      } }, "Löschen"))));
  return card;
}

/* ---------- E-Mail-Einstellungen (SMTP & Admin-Adresse) ---------- */
async function showSettings() {
  state.selectedId = null;
  state.creating = false;
  renderSidebar();
  const main = $("#studio-main");
  main.innerHTML = "";

  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "⚙ E-Mail-Einstellungen"));
  panel.appendChild(el("p", { style: "color:var(--text-dim);margin-bottom:18px" },
    "Hier hinterlegst du die Empfänger-Adresse für das Kontaktformular und " +
    "die SMTP-Zugangsdaten für den Versand. Das Passwort wird verschlüsselt " +
    "in data/config.json gespeichert."));

  const statusBadge = el("div", { class: "settings-status" }, "lädt …");
  panel.appendChild(statusBadge);

  let cfg = {};
  try {
    cfg = await fetch("/api/admin/config").then(r => r.json());
  } catch (err) {
    panel.appendChild(el("p", { style: "color:#ff6b6f" }, "Fehler: " + err.message));
    main.appendChild(panel);
    return;
  }

  if (cfg.smtp_configured) {
    statusBadge.className = "settings-status ok";
    statusBadge.textContent = "✓ SMTP ist konfiguriert. Kontaktnachrichten werden per Mail versendet.";
  } else {
    statusBadge.className = "settings-status warn";
    statusBadge.textContent = "⚠ Noch nicht vollständig konfiguriert. Nachrichten landen nur im Posteingang.";
  }

  const form = el("form", { class: "settings-form" });

  function field(label, name, type, value, opts = {}) {
    const input = el("input", {
      name, type, value: value ?? "", autocomplete: "off",
      ...(opts.placeholder ? { placeholder: opts.placeholder } : {}),
    });
    return el("div", { class: "field" },
      el("label", {}, label),
      input,
      opts.hint ? el("div", { class: "image-hint" }, opts.hint) : null);
  }

  function checkbox(label, name, checked) {
    const input = el("input", { type: "checkbox", name });
    if (checked) input.checked = true;
    return el("label", { class: "settings-check" }, input,
      el("span", {}, label));
  }

  form.appendChild(el("h3", { style: "margin-top:0" }, "💚 Plattform-Spenden"));
  form.appendChild(field("PayPal der Plattform (E-Mail oder PayPal.me-Link)",
    "platform_paypal", "text", cfg.platform_paypal,
    { placeholder: "z. B. paypal.me/riotmusic oder admin@beispiel.de",
      hint: "Wenn gesetzt, erscheint auf der Startseite ein „♥ Plattform unterstützen“-Button. " +
            "Spenden gehen an dieses Konto. Leer lassen = kein Button. " +
            "PayPal.me-Link schützt deine E-Mail." }));

  form.appendChild(el("h3", {}, "Empfänger (Kontaktformular)"));
  form.appendChild(field("Admin-E-Mail (Empfänger der Kontaktanfragen)",
    "admin_email", "email", cfg.admin_email,
    { placeholder: "admin@beispiel.de",
      hint: "Wird im Reply-To NICHT überschrieben – Antworten gehen direkt an Absender:in." }));

  form.appendChild(el("h3", {}, "SMTP-Server"));
  const row1 = el("div", { class: "field-row" },
    field("SMTP-Host", "smtp_host", "text", cfg.smtp_host,
      { placeholder: "smtp.beispiel.de" }),
    field("Port", "smtp_port", "number", cfg.smtp_port || 587));
  form.appendChild(row1);

  form.appendChild(field("SMTP-Benutzer", "smtp_user", "text", cfg.smtp_user,
    { placeholder: "meistens identisch mit der E-Mail" }));
  form.appendChild(field("SMTP-Passwort", "smtp_password", "password",
    cfg.smtp_password,
    { hint: "Maske '********' bedeutet: Passwort ist gespeichert. Leerlassen = unverändert übernehmen." }));
  form.appendChild(field("Absender (From-Adresse)", "smtp_from", "email",
    cfg.smtp_from, { placeholder: "wird oft gleich zur Admin-Adresse" }));

  const checks = el("div", { class: "settings-checks" },
    checkbox("STARTTLS verwenden (Port 587)", "smtp_use_tls", cfg.smtp_use_tls),
    checkbox("SSL/TLS direkt verwenden (Port 465)", "smtp_use_ssl", cfg.smtp_use_ssl));
  form.appendChild(checks);

  const presetHint = el("div", { class: "image-hint", style: "margin-top:6px" },
    "Häufige Anbieter: Gmail → smtp.gmail.com:587 (STARTTLS, App-Passwort). " +
    "mailbox.org / Strato → :465 (SSL). Posteo → smtp.posteo.de:587 (STARTTLS).");
  form.appendChild(presetHint);

  // -------- Fingerprinting-Sektion --------
  form.appendChild(el("h3", {}, "🎧 Audio-Fingerprinting"));

  const fpStatusBox = el("div", { class: "settings-status" }, "lädt …");
  form.appendChild(fpStatusBox);

  fetch("/api/admin/fingerprint/status").then(r => r.json()).then((s) => {
    const parts = [];
    parts.push(s.fpcalc_available
      ? `✓ fpcalc gefunden (${s.fpcalc_path || "?"})`
      : "✗ fpcalc NICHT installiert — bitte nach backend/bin/ kopieren");
    parts.push(s.acoustid_configured
      ? "✓ AcoustID-Key gesetzt"
      : "○ Kein AcoustID-Key (nur lokale Duplikat-Erkennung)");
    parts.push(`Modus: ${s.mode}`);
    parts.push(`${s.stored_count} Fingerprints gespeichert`);
    fpStatusBox.textContent = parts.join(" · ");
    fpStatusBox.className = "settings-status " +
      (s.fpcalc_available ? "ok" : "warn");
  }).catch(() => {});

  form.appendChild(field("AcoustID-API-Key", "acoustid_api_key", "text",
    cfg.acoustid_api_key,
    { placeholder: "kostenlos: https://acoustid.org/api-key",
      hint: "Leer = nur lokale Duplikatprüfung. Mit Key wird zusätzlich gegen ~80 Mio bekannte Songs abgeglichen." }));

  const modeWrap = el("div", { class: "field" },
    el("label", {}, "Verhalten bei Match in AcoustID-Datenbank"),
    el("select", { name: "fingerprint_mode" },
      el("option", { value: "strict", selected: cfg.fingerprint_mode === "strict" },
        "strict — Upload blockieren (empfohlen)"),
      el("option", { value: "warn", selected: cfg.fingerprint_mode === "warn" },
        "warn — Upload zulassen, nur protokollieren"),
      el("option", { value: "off", selected: cfg.fingerprint_mode === "off" },
        "off — AcoustID gar nicht erst befragen")),
    el("div", { class: "image-hint" },
      "Lokale Duplikat-Erkennung (identische Datei) blockiert IMMER, unabhängig vom Modus."));
  form.appendChild(modeWrap);

  form.appendChild(el("div", { class: "image-hint", style: "margin-top:6px" },
    "Installation des fpcalc-Binarys (Chromaprint): ",
    el("a", { href: "https://acoustid.org/chromaprint", target: "_blank" },
      "acoustid.org/chromaprint"),
    ". Lege die Binary nach backend/bin/."));

  // Backfill-Knopf für Alt-Tracks ohne Dauer
  const backfillBtn = el("button", { type: "button", class: "ghost-btn",
    style: "margin-top:10px",
    onclick: async () => {
      backfillBtn.disabled = true;
      backfillBtn.textContent = "Lese Audiodateien …";
      try {
        const r = await fetch("/api/admin/tracks/backfill-durations",
                              { method: "POST" });
        if (!r.ok) {
          let d = `Fehler ${r.status}`;
          try { d = (await r.json()).detail || d; } catch {}
          throw new Error(d);
        }
        const data = await r.json();
        toast(`Dauer für ${data.updated} Track(s) nachgetragen ` +
              `(${data.skipped} hatten schon eine, ${data.failed} fehlgeschlagen).`,
              "ok");
      } catch (err) {
        toast("Fehler: " + err.message, "error");
      } finally {
        backfillBtn.disabled = false;
        backfillBtn.textContent = "⏱ Fehlende Tracklängen nachtragen";
      }
    } }, "⏱ Fehlende Tracklängen nachtragen");
  form.appendChild(backfillBtn);

  const status = el("div", { class: "contact-status", style: "margin-top:14px" });
  const saveBtn = el("button", { type: "submit", class: "primary-btn" }, "Speichern");
  const testBtn = el("button", { type: "button", class: "ghost-btn",
    onclick: async () => {
      status.className = "contact-status";
      status.textContent = "Sende Test-Mail …";
      try {
        const res = await fetch("/api/admin/config/test-mail", { method: "POST" });
        if (!res.ok) {
          let detail = `Fehler ${res.status}`;
          try { detail = (await res.json()).detail || detail; } catch {}
          throw new Error(detail);
        }
        status.className = "contact-status ok";
        status.textContent = "✓ Test-Mail erfolgreich versendet. Schau in dein Postfach.";
      } catch (err) {
        status.className = "contact-status error";
        status.textContent = "✗ " + err.message;
      }
    } }, "✉ Test-Mail senden");

  form.appendChild(el("div", { class: "btn-row" }, saveBtn, testBtn, status));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const payload = {
      admin_email: fd.get("admin_email") || "",
      smtp_host: fd.get("smtp_host") || "",
      smtp_port: parseInt(fd.get("smtp_port") || "587", 10) || 587,
      smtp_user: fd.get("smtp_user") || "",
      smtp_password: fd.get("smtp_password") || "",
      smtp_from: fd.get("smtp_from") || "",
      smtp_use_tls: fd.get("smtp_use_tls") === "on",
      smtp_use_ssl: fd.get("smtp_use_ssl") === "on",
      acoustid_api_key: fd.get("acoustid_api_key") || "",
      fingerprint_mode: fd.get("fingerprint_mode") || "strict",
      platform_paypal: fd.get("platform_paypal") || "",
    };
    // Wenn das Passwort-Feld leer ist, schicke die Maske – Backend lässt
    // den gespeicherten Wert dann unverändert.
    if (!payload.smtp_password) payload.smtp_password = "********";

    status.className = "contact-status";
    status.textContent = "Speichere …";
    try {
      const res = await fetch("/api/admin/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = `Fehler ${res.status}`;
        try { detail = (await res.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      const updated = await res.json();
      status.className = "contact-status ok";
      status.textContent = "✓ Gespeichert.";
      // Status-Badge auffrischen
      if (updated.smtp_configured) {
        statusBadge.className = "settings-status ok";
        statusBadge.textContent = "✓ SMTP ist konfiguriert. Kontaktnachrichten werden per Mail versendet.";
      } else {
        statusBadge.className = "settings-status warn";
        statusBadge.textContent = "⚠ Noch nicht vollständig konfiguriert. Nachrichten landen nur im Posteingang.";
      }
      // Passwortfeld nach dem Speichern auf Maske setzen
      form.querySelector("input[name=smtp_password]").value = "";
    } catch (err) {
      status.className = "contact-status error";
      status.textContent = "✗ " + err.message;
    }
  });

  panel.appendChild(form);
  main.appendChild(panel);
}

/* ---------- Nutzungs-Übersicht (Dashboard) ---------- */
async function showOverview() {
  state.selectedId = null;
  state.creating = false;
  renderSidebar();
  const main = $("#studio-main");
  main.innerHTML = "";

  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "📊 Übersicht"));
  const body = el("div", {}, "Laden …");
  panel.appendChild(body);
  main.appendChild(panel);

  let data;
  try {
    data = await fetch("/api/admin/overview").then(r => r.json());
  } catch (err) {
    body.innerHTML = "";
    body.appendChild(el("p", { style: "color:#ff6b6f" }, "Fehler: " + err.message));
    return;
  }
  body.innerHTML = "";

  // Kennzahlen-Kacheln
  const t = data.totals, d = data.donations;
  const stat = (num, label) => el("div", { class: "ov-stat" },
    el("span", { class: "ov-num" }, String(num)),
    el("span", { class: "ov-label" }, label));
  body.appendChild(el("div", { class: "ov-stats" },
    stat(t.plays, "Plays gesamt"),
    stat(t.artists, "Künstler:innen"),
    stat(t.releases, "Releases"),
    stat(t.tracks, "Songs"),
    stat(d.platformClicks, "Spenden-Klicks (Plattform)"),
    stat(d.artistClicks, "Spenden-Klicks (Künstler:innen)")));

  // Hinweis zur Aussagekraft der Klicks
  body.appendChild(el("p", { class: "image-hint", style: "margin:14px 0 22px" },
    "ℹ️ „Spenden-Klicks“ zählen, wie oft ein Spenden-Button gedrückt wurde — " +
    "nicht die tatsächlichen Spenden oder Beträge. Echte Eingänge siehst du nur " +
    "in deinem PayPal-Konto (die Plattform ist nicht am Zahlungsfluss beteiligt)."));

  // Tabelle: pro Künstler:in
  body.appendChild(el("h3", {}, "Nach Künstler:in (nach Plays sortiert)"));
  if (!data.artists.length) {
    body.appendChild(el("p", { style: "color:var(--text-dim)" }, "Noch keine Künstler:innen."));
    return;
  }
  const table = el("table", { class: "ov-table" });
  table.appendChild(el("tr", {},
    el("th", {}, "Künstler:in"),
    el("th", {}, "Plays"),
    el("th", {}, "Songs"),
    el("th", {}, "Spenden-Klicks"),
    el("th", {}, "Status")));
  data.artists.forEach((a) => {
    const status = !a.public ? "🕓 unbestätigt"
      : (a.hasDonate ? "💚 Spenden aktiv" : "öffentlich");
    table.appendChild(el("tr", {},
      el("td", {}, el("a", { href: `/#/artist/${a.id}`, target: "_blank" }, a.name)),
      el("td", {}, String(a.plays)),
      el("td", {}, String(a.tracks)),
      el("td", {}, String(a.donateClicks)),
      el("td", { style: "color:var(--text-dim)" }, status)));
  });
  body.appendChild(table);
}

/* ---------- Auszahlungsübersicht ---------- */
async function showPayout() {
  state.selectedId = null;
  state.creating = false;
  renderSidebar();
  const main = $("#studio-main");
  main.innerHTML = "";

  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h2", {}, "💰 Monatliche Auszahlung"));
  panel.appendChild(el("p", { style: "color:var(--text-dim);margin-bottom:18px" },
    "Gib den Gesamtbetrag ein, der im zentralen PayPal-Konto eingegangen ist. " +
    "Der Betrag wird gleichmäßig auf alle Künstler:innen mit hinterlegter PayPal-Adresse verteilt."));

  const form = el("form", { class: "inline-form", style: "margin-bottom:22px" });
  form.appendChild(el("div", { class: "field", style: "flex:1" },
    el("label", {}, "Gesamtbetrag im Topf (€)"),
    el("input", { name: "total", type: "number", step: "0.01", min: "0", value: "0", required: true, style: "font-size:1.1rem" })));
  form.appendChild(el("button", { type: "submit", class: "primary-btn" }, "Berechnen"));
  panel.appendChild(form);

  const result = el("div", { id: "payout-result" });
  panel.appendChild(result);
  main.appendChild(panel);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const total = parseFloat($("input[name=total]", form).value) || 0;
    try {
      const data = await apiGet(`/api/manage/payout?total=${total}`);
      renderPayoutResult(result, data);
    } catch (err) { toast("Fehler: " + err.message, "error"); }
  });
}

function renderPayoutResult(container, data) {
  container.innerHTML = "";
  if (!data.count) {
    container.appendChild(el("p", { style: "color:var(--accent-soft)" },
      "Keine Künstler:innen mit PayPal-Adresse gefunden. Bitte die Künstler:innen bitten, ihre PayPal-Adresse im Profil zu hinterlegen."));
    return;
  }

  // Zusammenfassung
  const summary = el("div", { class: "payout-summary" });
  summary.appendChild(el("div", { class: "payout-stat" },
    el("span", { class: "payout-num" }, `${data.total.toFixed(2)} €`),
    el("span", { class: "payout-label" }, "Gesamtbetrag")));
  summary.appendChild(el("div", { class: "payout-stat" },
    el("span", { class: "payout-num" }, String(data.count)),
    el("span", { class: "payout-label" }, "Empfänger:innen")));
  summary.appendChild(el("div", { class: "payout-stat" },
    el("span", { class: "payout-num" }, `${data.perArtist.toFixed(2)} €`),
    el("span", { class: "payout-label" }, "pro Künstler:in")));
  container.appendChild(summary);

  // Tabelle
  if (data.total > 0) {
    const table = el("table", { class: "payout-table" });
    table.appendChild(el("thead", {},
      el("tr", {},
        el("th", {}, "Künstler:in"),
        el("th", {}, "PayPal"),
        el("th", {}, "Songs"),
        el("th", { style: "text-align:right" }, "Betrag"))));
    const tbody = el("tbody");
    data.eligible.forEach((a) => {
      tbody.appendChild(el("tr", {},
        el("td", {}, a.name),
        el("td", {},
          el("code", { class: "paypal-addr", onclick: () => { navigator.clipboard.writeText(a.paypal); toast("Kopiert: " + a.paypal, "ok"); } },
            a.paypal)),
        el("td", {}, String(a.trackCount)),
        el("td", { style: "text-align:right;font-weight:700" }, `${a.amount.toFixed(2)} €`)));
    });
    table.appendChild(tbody);
    container.appendChild(table);
    container.appendChild(el("p", { class: "image-hint" },
      "Klicke auf eine PayPal-Adresse, um sie zu kopieren. Dann in PayPal → Geld senden einfügen."));
  }

  // Künstler:innen ohne PayPal
  if (data.withoutPaypal.length) {
    container.appendChild(el("div", { style: "margin-top:18px;padding:12px;background:var(--bg-elev);border-radius:8px;border:1px solid var(--border)" },
      el("strong", { style: "color:var(--accent-soft)" }, "⚠ Ohne PayPal-Adresse: "),
      el("span", { style: "color:var(--text-dim)" }, data.withoutPaypal.join(", ") +
        " — diese Künstler:innen erhalten keine Auszahlung, bis sie ihre PayPal-Adresse im Profil hinterlegen.")));
  }
}

(async function init() {
  try {
    const me = await apiGet("/api/auth/me");
    if (me.authenticated && me.role === "admin") {
      return startAdmin();
    }
    const { exists } = await apiGet("/api/auth/admin-exists");
    renderAdminLogin(exists ? "login" : "bootstrap",
                     me.authenticated ? me.email : null);
  } catch (err) {
    toast("Backend nicht erreichbar: " + err.message, "error");
  }
})();
