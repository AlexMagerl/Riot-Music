/* Riot Music — Künstlerbereich (Self-Service mit Login) */
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
const initials = (name) => (name || "?").split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase();
function colorOf(str) {
  let h = 0;
  for (let i = 0; i < (str || "").length; i++) h = (h * 31 + str.charCodeAt(i)) % 360;
  return `linear-gradient(135deg, hsl(${h} 62% 38%), hsl(${(h + 40) % 360} 64% 24%))`;
}
const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

let toastTimer;
function toast(msg, kind = "ok") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), 3000);
}

async function apiSend(method, url, body) {
  const res = await fetch(url, { method, body });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}
const apiJson = (url) => fetch(url).then((r) => r.json());

const state = { artist: null, email: null, genres: [] };
const root = () => $("#root");

/* ====================================================================
   AUTH-SCREEN (Login / Registrierung)
   ==================================================================== */
function renderAuth(mode = "login") {
  $("#top-actions").innerHTML = "";
  $("#top-actions").appendChild(el("a", { href: "/", class: "back-link" }, "← Zur Hörer-Ansicht"));

  const r = root();
  r.innerHTML = "";

  const tabs = el("div", { class: "auth-tabs" },
    el("button", { class: "auth-tab" + (mode === "login" ? " active" : ""),
      onclick: () => renderAuth("login") }, "Anmelden"),
    el("button", { class: "auth-tab" + (mode === "register" ? " active" : ""),
      onclick: () => renderAuth("register") }, "Registrieren"));

  const form = el("form", { class: "auth-form" });
  form.appendChild(el("div", { class: "field" }, el("label", {}, "E-Mail"),
    el("input", { name: "email", type: "email", required: true, autocomplete: "email" })));
  form.appendChild(el("div", { class: "field" }, el("label", {}, "Passwort"),
    el("input", { name: "password", type: "password", required: true, minlength: 8,
      autocomplete: mode === "login" ? "current-password" : "new-password" })));

  let captchaState = null;
  if (mode === "register") {
    form.appendChild(el("div", { class: "field" }, el("label", {}, "Künstlername"),
      el("input", { name: "artistName", required: true, placeholder: "z.B. Johnny Guitar" })));
    // Honeypot: für Menschen unsichtbar, Bots füllen es trotzdem aus.
    form.appendChild(el("div", {
      "aria-hidden": "true",
      style: "position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none",
    },
      el("label", {}, "Website (bitte leer lassen)"),
      el("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off" })));
    const captchaLabel = el("label", {}, "Anti-Bot-Frage");
    const captchaQ = el("div", { class: "captcha-q", style: "padding:8px 0;color:var(--text-dim)" }, "lädt …");
    const captchaInput = el("input", { name: "captchaAnswer", required: true,
      inputmode: "numeric", autocomplete: "off", placeholder: "Antwort" });
    const captchaIdInput = el("input", { type: "hidden", name: "captchaId" });
    const reloadCaptcha = async () => {
      try {
        captchaState = await fetch("/api/auth/captcha").then(r => r.json());
        captchaQ.textContent = captchaState.question;
        captchaIdInput.value = captchaState.id;
        captchaInput.value = "";
      } catch {
        captchaQ.textContent = "Captcha konnte nicht geladen werden.";
      }
    };
    form.appendChild(el("div", { class: "field" }, captchaLabel, captchaQ, captchaInput, captchaIdInput));

    // Pflicht-Häkchen: AGB & Rechte-Versicherung
    const agbBox = el("input", { type: "checkbox", name: "acceptAgb", required: true });
    form.appendChild(el("label", { class: "agb-accept" }, agbBox,
      el("span", {},
        "Ich versichere, dass ich ",
        el("strong", {}, "alle Rechte"),
        " an meinen Uploads halte, kein Material Dritter ohne Lizenz verwende und ",
        el("strong", {}, "nicht durch eine Verwertungsgesellschaft (z. B. GEMA) gebunden"),
        " bin (oder die hochgeladenen Werke nicht deren Wahrnehmung unterliegen). " +
        "Ich akzeptiere die ",
        el("a", { href: "/agb.html", target: "_blank" }, "AGB"),
        " und die ",
        el("a", { href: "/datenschutz.html", target: "_blank" }, "Datenschutzerklärung"),
        ".")));

    form.appendChild(el("p", { class: "auth-hint" },
      "Mit der Registrierung wird automatisch dein Künstlerprofil angelegt. Genre & Details legst du danach im Profil fest."));
    reloadCaptcha();
    form._reloadCaptcha = reloadCaptcha;
  }

  form.appendChild(el("button", { type: "submit", class: "primary-btn full" },
    mode === "login" ? "Anmelden" : "Profil anlegen"));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const url = mode === "login" ? "/api/auth/login" : "/api/auth/register";
    const emailVal = fd.get("email");
    try {
      const btn = $("button[type=submit]", form); btn.disabled = true;
      const data = await apiSend("POST", url, fd);

      // Double-Opt-In: Registrierung wartet auf E-Mail-Bestätigung.
      if (data.pending) {
        renderPendingVerification(data.email);
        return;
      }
      if (data.verificationMailFailed) {
        toast("Konto erstellt — Bestätigungsmail konnte nicht gesendet werden, " +
              "du bist direkt freigeschaltet.", "ok");
      }

      state.artist = data.artist;
      state.email = data.email;
      toast(mode === "login" ? "Willkommen zurück!" : "Profil angelegt — leg los!", "ok");
      if (!state.artist) {
        console.error("state.artist is null after login/register");
        toast("Fehler: Künstler-Daten nicht geladen", "error");
        return;
      }
      setTimeout(() => renderEditor(), 100);
    } catch (err) {
      const btn = $("button[type=submit]", form); if (btn) btn.disabled = false;
      // Login mit noch nicht bestätigter E-Mail -> Bestätigungs-Screen anbieten.
      if (mode === "login" && /bestätige/i.test(err.message)) {
        renderPendingVerification(emailVal, err.message);
        return;
      }
      toast("Fehler: " + err.message, "error");
      if (mode === "register" && form._reloadCaptcha) form._reloadCaptcha();
    }
  });

  r.appendChild(el("div", { class: "auth-card" },
    el("h1", {}, "Künstlerbereich"),
    el("p", { class: "auth-sub" }, "Verwalte dein eigenes Profil, deine Releases und Songs."),
    tabs, form));
}

/* ---- Double-Opt-In: Hinweis „bitte E-Mail bestätigen" ---- */
function renderPendingVerification(email, customMsg) {
  $("#top-actions").innerHTML = "";
  $("#top-actions").appendChild(el("a", { href: "/", class: "back-link" }, "← Zur Hörer-Ansicht"));
  const r = root();
  r.innerHTML = "";

  const msg = customMsg ||
    "Fast geschafft! Wir haben dir eine Bestätigungsmail geschickt. " +
    "Bitte klicke auf den Link in der E-Mail, um dein Profil zu aktivieren.";

  const status = el("div", { class: "contact-status", style: "min-height:1.2em" });

  const resendBtn = el("button", { class: "primary-btn full", onclick: async () => {
    resendBtn.disabled = true;
    status.className = "contact-status";
    status.textContent = "Sende erneut …";
    try {
      const fd = new FormData();
      fd.set("email", email || "");
      await apiSend("POST", "/api/auth/resend-verification", fd);
      status.className = "contact-status ok";
      status.textContent = "✓ Falls ein Konto existiert, ist die Mail unterwegs. Schau auch im Spam-Ordner.";
    } catch (err) {
      status.className = "contact-status error";
      status.textContent = "✗ " + err.message;
    } finally {
      setTimeout(() => { resendBtn.disabled = false; }, 4000);
    }
  } }, "Bestätigungsmail erneut senden");

  r.appendChild(el("div", { class: "auth-card" },
    el("div", { style: "font-size:2.4rem;text-align:center" }, "📬"),
    el("h1", {}, "E-Mail bestätigen"),
    el("p", { class: "auth-sub" }, msg),
    email ? el("p", { class: "auth-hint" }, "Adresse: " + email) : null,
    resendBtn,
    status,
    el("div", { style: "margin-top:14px;text-align:center" },
      el("a", { href: "#", class: "back-link",
        onclick: (e) => { e.preventDefault(); renderAuth("login"); } },
        "← Zurück zur Anmeldung"))));
}

/* ====================================================================
   EDITOR (eingeloggt)
   ==================================================================== */
function imageField({ name, round, currentUrl, size = 96, hint }) {
  const preview = el("div", { class: "image-preview" + (round ? " round" : ""),
    style: `width:${size}px;height:${size}px` });
  if (currentUrl) preview.appendChild(el("img", { src: currentUrl, alt: "" }));
  else preview.textContent = "🖼";
  const input = el("input", { type: "file", name, accept: "image/jpeg,.jpg,.jpeg" });
  input.addEventListener("change", () => {
    const f = input.files[0];
    if (!f) return;
    preview.innerHTML = "";
    preview.appendChild(el("img", { src: URL.createObjectURL(f), alt: "" }));
  });
  return el("div", { class: "image-field" }, preview,
    el("div", {}, input, hint && el("div", { class: "image-hint" }, hint)));
}

function renderGuidelines() {
  const guide = el("aside", { class: "editor-sidebar" });

  guide.appendChild(el("h3", {}, "📋 Richtlinien & Anleitung"));

  guide.appendChild(el("p", { class: "legal-text", style: "margin-top:0" },
    "Die ausführlichen rechtlichen Bedingungen findest du in den ",
    el("a", { href: "/agb.html", target: "_blank" }, "AGB"),
    ". Die folgenden Punkte sind die wichtigsten Pflichten in Kurzform."));

  // -------------------- ANLEITUNG --------------------
  guide.appendChild(el("section", { class: "guide-section" },
    el("h4", {}, "1. Deine Künstleridentität"),
    el("p", {}, "Lege Künstlernamen, Bio, Profilfoto und Banner an. Tritt unter dem Namen auf, den du nach außen verwenden willst — fiktive Identitäten sind erlaubt, Imitationen realer Personen nicht."),
    el("ul", {},
      el("li", {}, "Künstlername ist Pflicht"),
      el("li", {}, "Foto & Banner: JPEG, max. 5 MB"),
      el("li", {}, "Bio: kurze Selbstvorstellung empfohlen"))));

  guide.appendChild(el("section", { class: "guide-section" },
    el("h4", {}, "2. Musik veröffentlichen"),
    el("p", {}, "Lade einzelne Songs oder ganze Bündel (Album / EP / Single) hoch. Jeder Upload ist eine Veröffentlichung — bitte erst hochladen, wenn der Mix final ist."),
    el("ul", {},
      el("li", {}, "Audioformat: MP3"),
      el("li", {}, "Cover: JPEG, mindestens 500 × 500 px empfohlen"),
      el("li", {}, "Genre frei wählbar"))));

  guide.appendChild(el("section", { class: "guide-section" },
    el("h4", {}, "3. Musikvideos"),
    el("p", {}, "YouTube- oder Vimeo-Links direkt einbetten. Kopiere einfach die URL aus dem Browser."),
    el("ul", {},
      el("li", {}, "Max. 6 Videos pro Profil"),
      el("li", {}, "Unterstützt: youtube.com, youtu.be, vimeo.com"))));

  guide.appendChild(el("section", { class: "guide-section" },
    el("h4", {}, "4. Spenden"),
    el("p", {}, "Trägst du eine PayPal-Adresse oder einen PayPal.me-Link ein, erscheint auf deinem Profil ein „♥ Spenden“-Button. Spenden gehen zu 100% direkt an dich — wir wickeln nichts ab."),
    el("ul", {},
      el("li", {}, "Ohne Eintrag: kein Spenden-Button"),
      el("li", {}, "PayPal.me-Link schützt deine E-Mail"),
      el("li", {}, "Steuerliche Behandlung liegt bei dir"),
      el("li", {}, "Jederzeit änderbar"))));

  guide.appendChild(el("hr"));

  // -------------------- KERN: RECHTE-VERSICHERUNG --------------------
  guide.appendChild(el("section", { class: "guide-section danger" },
    el("h4", {}, "⚖️ Rechte an deinen Uploads (Pflicht-Lektüre)"),
    el("p", { class: "legal-text" },
      "Mit jedem Upload bestätigst du, dass du sämtliche Rechte an dem Werk hältst. " +
      "Riot Music befindet sich in Stufe 1: ",
      el("strong", {}, "nur eigene, selbst-vermarktete Werke"),
      " sind erlaubt. Details: AGB § 4."),

    el("ul", { class: "legal-list" },
      el("li", {}, el("strong", {}, "Alleinige Urheberin: "),
        "Du hast den Song selbst komponiert, getextet und aufgenommen — oder hast mit allen Mitwirkenden (Co-Autor:innen, Bandmitglieder, Producer) schriftliche Vereinbarungen, die dir die alleinige Verwertung erlauben."),
      el("li", {}, el("strong", {}, "Keine fremden Samples / Loops: "),
        "Kein urheberrechtlich geschütztes Material Dritter, es sei denn lizenzfrei (CC0 o. ä.) oder schriftlich freigegeben. Bewahre die Nachweise mindestens 5 Jahre auf."),
      el("li", {}, el("strong", {}, "Keine Exklusivbindungen: "),
        "Dein Werk ist nicht durch Verträge mit Labels, Verlagen oder Aggregatoren blockiert, die einer Veröffentlichung hier entgegenstünden."),
      el("li", {}, el("strong", {}, "GEMA / GVL: "),
        "Wenn du Mitglied einer Verwertungsgesellschaft bist, melde das beim Upload an. Werke, die der Wahrnehmung der GEMA unterliegen, kannst du ",
        el("em", {}, "derzeit nicht"),
        " hochladen — Riot Music hat noch keinen Wahrnehmungsvertrag. GEMA-freie Werke und vor-GEMA-Werke sind ok."),
      el("li", {}, el("strong", {}, "Persönlichkeits- & Markenrechte: "),
        "Erscheinen andere Personen in Aufnahmen, Bildern oder Videos, brauchst du deren schriftliche Einwilligung. Keine fremden Logos / Marken ohne Erlaubnis."),
      el("li", {}, el("strong", {}, "Belegpflicht: "),
        "Bei berechtigten Zweifeln musst du uns auf Anfrage Nachweise (Splits, Co-Writer-Bestätigungen, Sample-Clearances) vorlegen.")),

    el("p", { class: "legal-text" },
      el("strong", {}, "Freistellung: "),
      "Sollten Dritte wegen einer Rechtsverletzung gegen uns vorgehen, stellst du uns von diesen Ansprüchen frei (AGB § 10).")));

  // -------------------- VERBOTENE INHALTE --------------------
  guide.appendChild(el("section", { class: "guide-section danger" },
    el("h4", {}, "🚫 Verbotene Inhalte"),
    el("p", { class: "legal-text" }, "Untersagt sind insbesondere:"),
    el("ul", { class: "legal-list" },
      el("li", {}, "Inhalte, die Rechte Dritter verletzen (Urheber-, Marken-, Persönlichkeits-, Leistungsschutzrechte)"),
      el("li", {}, "Nach deutschem oder europäischem Recht strafbare Inhalte (§§ 86, 86a, 130, 131, 184, 184b StGB u. a.)"),
      el("li", {}, "Sexuell explizites Material — insbesondere jede Darstellung Minderjähriger"),
      el("li", {}, "Aufrufe zu oder Verherrlichung von Gewalt, Selbstverletzung oder Straftaten"),
      el("li", {}, "Diskriminierung wegen Herkunft, Religion, Geschlecht, Geschlechtsidentität, sexueller Orientierung oder Behinderung"),
      el("li", {}, "Extremistische, terroristische oder verfassungsfeindliche Botschaften"),
      el("li", {}, "Schadsoftware oder Links darauf"),
      el("li", {}, "Manipulation von Plays / Unterstützungsbeiträgen (Bots, Multi-Accounts)"))));

  // -------------------- SANKTIONEN --------------------
  guide.appendChild(el("section", { class: "guide-section" },
    el("h4", {}, "⚠️ Sanktionen"),
    el("p", { class: "legal-text" },
      "Bei Verstößen gegen die Rechte-Klausel oder gegen verbotene Inhalte kann die Betreiberin dein Profil ",
      el("strong", {}, "ohne vorherige Ankündigung und unwiderruflich"),
      " sperren oder löschen. Bereits erhaltene Unterstützungsbeiträge müssen in solchen Fällen nicht erstattet werden (AGB § 8). Bei unklarer Rechtslage werden Inhalte zunächst gesperrt und du wirst zur Stellungnahme aufgefordert (AGB § 9)."),
    el("p", { class: "legal-text" },
      el("strong", {}, "Notice & Take-Down: "),
      "Wenn du selbst eine Rechtsverletzung melden möchtest, nutze das ",
      el("a", { href: "/#/kontakt", target: "_blank" }, "Kontaktformular"), ".")));

  // -------------------- DATEN & LÖSCHUNG --------------------
  guide.appendChild(el("section", { class: "guide-section" },
    el("h4", {}, "📜 Daten & Selbstlöschung"),
    el("p", { class: "legal-text" },
      el("strong", {}, "Datenschutz: "),
      "Deine E-Mail dient nur Authentifizierung und Auszahlung. Details in der ",
      el("a", { href: "/datenschutz.html", target: "_blank" }, "Datenschutzerklärung"), "."),
    el("p", { class: "legal-text" },
      el("strong", {}, "Recht auf Löschung: "),
      "In der „Gefahrenzone“ unten im Profil kannst du dein Konto jederzeit selbst löschen. Wir entfernen deine Inhalte dann innerhalb von 30 Tagen.")));

  return guide;
}

function renderEditor() {
  const a = state.artist;
  $("#top-actions").innerHTML = "";
  $("#top-actions").appendChild(el("a", { href: `/#/artist/${a.id}`, class: "back-link", target: "_blank" },
    "↗ Öffentliche Seite ansehen"));
  $("#top-actions").appendChild(el("span", { class: "logged-as" }, state.email));
  $("#top-actions").appendChild(el("button", { class: "ghost-btn small", onclick: logout }, "Abmelden"));

  const r = root();
  r.innerHTML = "";

  // Zwei-Spalten-Layout: Inhalt links, Anleitung rechts
  const mainContainer = el("div", { class: "editor-layout" });
  const leftColumn = el("div", { class: "editor-main" });

  leftColumn.appendChild(renderProfilePanel(a));
  leftColumn.appendChild(renderUploadPanel(a));
  leftColumn.appendChild(renderReleasesPanel(a));

  mainContainer.appendChild(leftColumn);
  mainContainer.appendChild(renderGuidelines());

  r.appendChild(mainContainer);
}

/* ---- Profil (Kopf, wie auf der Künstlerseite – nur editierbar) ---- */
/* ---- Video-Liste (dynamisch) ---- */
function addVideoField(container, url = "") {
  const list = container.parentElement ? container : container;
  const count = list.querySelectorAll(".video-input").length;
  if (count >= 6) {
    toast("Max. 6 Videos möglich.", "error");
    return;
  }
  const row = el("div", { class: "video-input", style: "display:flex;gap:8px;margin-bottom:8px" },
    el("input", { type: "url", class: "video-url-input", value: url,
      placeholder: "https://youtube.com/watch?v=... oder https://vimeo.com/..." }),
    el("button", { type: "button", class: "danger-btn",
      onclick: () => row.remove(),
      style: "padding:8px 12px" }, "✕"));
  list.appendChild(row);
}

function bannerField(currentUrl) {
  const wrap = el("div", { class: "banner-field" });
  const preview = el("div", { class: "banner-preview" });
  if (currentUrl) preview.style.backgroundImage = `url(${currentUrl})`;
  const input = el("input", { type: "file", name: "banner", accept: "image/jpeg,.jpg,.jpeg" });
  input.addEventListener("change", () => {
    const f = input.files[0];
    if (!f) return;
    preview.style.backgroundImage = `url(${URL.createObjectURL(f)})`;
  });
  const label = el("label", { class: "banner-upload-label" }, currentUrl ? "Banner ändern" : "Banner hochladen", input);
  wrap.appendChild(preview);
  wrap.appendChild(label);
  wrap.appendChild(el("div", { class: "image-hint" }, "Breitformat — wird auf 1400×400 zugeschnitten."));
  return wrap;
}

/* Plattform-Definitionen: [key, Icon, Label, Platzhalter] */
const SOCIAL_PLATFORMS = [
  ["website",    "🌐", "Website",      "https://deine-seite.de"],
  ["instagram",  "📷", "Instagram",    "https://instagram.com/dein.name"],
  ["facebook",   "📘", "Facebook",     "https://facebook.com/deineseite"],
  ["x",          "𝕏",  "X (Twitter)",  "https://x.com/deinname"],
  ["tiktok",     "🎵", "TikTok",       "https://tiktok.com/@deinname"],
  ["youtube",    "▶️", "YouTube",      "https://youtube.com/@deinkanal"],
  ["bandcamp",   "🅑",  "Bandcamp",     "https://deinname.bandcamp.com"],
  ["soundcloud", "☁️", "SoundCloud",   "https://soundcloud.com/deinname"],
  ["spotify",    "🎧", "Spotify",      "https://open.spotify.com/artist/…"],
  ["mastodon",   "🐘", "Mastodon",     "https://mastodon.social/@deinname"],
];

function renderProfilePanel(a) {
  const form = el("form", { class: "panel artist-edit-head" });
  form.appendChild(bannerField(a.banner));
  form.appendChild(imageField({ name: "image", round: true, currentUrl: a.image, size: 130,
    hint: "Klicken zum Ändern. Wird quadratisch zugeschnitten." }));

  const genreSummary = (a.genres && a.genres.length)
    ? a.genres.join(" · ") : "Noch kein Genre — setzt du pro Release/Song.";
  const fields = el("div", { class: "artist-edit-fields" },
    el("div", { class: "field" }, el("label", {}, "Künstlername"),
      el("input", { name: "name", value: a.name, required: true })),
    el("div", { class: "field" }, el("label", {}, "Ort"),
      el("input", { name: "location", value: a.location || "" })),
    el("div", { class: "field" }, el("label", {}, "Bio"),
      el("textarea", { name: "bio" }, a.bio || "")),
    el("div", { class: "field" }, el("label", {}, "Musikvideos (YouTube oder Vimeo, optional)"),
      el("div", { class: "videos-list", id: "videos-list" }),
      el("button", { type: "button", class: "ghost-btn",
        onclick: (e) => { e.preventDefault(); addVideoField($("#videos-list")); } }, "+ Video hinzufügen"),
      el("div", { class: "image-hint" },
        "Kopiere die URL direkt aus YouTube oder Vimeo. Max. 6 Videos.")),
    el("div", { class: "field" },
      el("label", {}, "Soziale Netzwerke & Links (optional)"),
      el("div", { class: "social-edit-grid" },
        SOCIAL_PLATFORMS.map(([key, icon, label, ph]) =>
          el("div", { class: "social-edit-row" },
            el("span", { class: "social-edit-ico", title: label }, icon),
            el("input", { type: "text", class: "social-input", "data-platform": key,
              value: (a.social && a.social[key]) || "", placeholder: ph,
              "aria-label": label })))),
      el("div", { class: "image-hint" },
        "Pro Netzwerk ein Link. Es werden nur Adressen der jeweiligen Plattform akzeptiert.")),
    el("div", { class: "field" }, el("label", {}, "Deine Genres (aus deinen Releases)"),
      el("div", { class: "genre-summary" }, genreSummary)),
    el("div", { class: "field payout-field" },
      el("label", {}, "PayPal für Spenden (E-Mail oder PayPal.me-Link)"),
      el("input", { name: "paypal", type: "text", value: a.paypal || "",
        placeholder: "z. B. paypal.me/deinname oder deine@email.de" }),
      el("div", { class: "image-hint" },
        "Sobald du etwas einträgst, erscheint auf deinem Profil ein „♥ Spenden“-Button. " +
        "Spenden gehen zu 100% direkt an dich. Tipp: Ein PayPal.me-Link schützt deine " +
        "E-Mail-Adresse besser als die direkte E-Mail. Feld leer lassen = kein Spenden-Button.")),
    el("div", { class: "btn-row" },
      el("button", { type: "submit", class: "primary-btn" }, "Profil speichern")),
    el("div", { class: "btn-row", style: "margin-top:30px;border-top:1px solid var(--border);padding-top:20px;" },
      el("p", { style: "color:var(--text-dim);font-size:0.9rem;margin-bottom:12px;" }, "⚠️ Gefahrenzone"),
      el("button", { type: "button", class: "danger-btn",
        onclick: showDeleteProfileDialog }, "Profil permanent löschen")));

  form.appendChild(fields);

  // Vorhandene Videos laden
  const videosList = $("#videos-list", form);
  if (a.videoUrls && Array.isArray(a.videoUrls)) {
    a.videoUrls.forEach((url) => addVideoField(videosList, url));
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    if (!fd.get("image")?.size) fd.delete("image");
    if (!fd.get("banner")?.size) fd.delete("banner");

    // Video-URLs sammeln
    const videoInputs = Array.from(form.querySelectorAll(".video-url-input"));
    const videoUrls = videoInputs.map(inp => inp.value.trim()).filter(v => v);
    fd.set("videoUrlsJson", JSON.stringify(videoUrls));

    // Social-Links sammeln
    const socialObj = {};
    form.querySelectorAll(".social-input").forEach((inp) => {
      const v = inp.value.trim();
      if (v) socialObj[inp.dataset.platform] = v;
    });
    fd.set("socialJson", JSON.stringify(socialObj));

    try {
      state.artist = await apiSend("PUT", "/api/studio/artist", fd);
      toast("Profil gespeichert.", "ok");
      renderEditor();
    } catch (err) { toast("Fehler: " + err.message, "error"); }
  });
  return form;
}

function genreDatalist() {
  const dl = el("datalist", { id: "genres-dl" });
  (state.genres || []).forEach((g) => dl.appendChild(el("option", { value: g })));
  return dl;
}

/* ---- Upload-Werkzeuge: Einzelsong ODER Bündel ---- */
function renderUploadPanel(a) {
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h3", {}, "Neue Musik veröffentlichen"));

  // Fingerprint-Status-Banner — zeigt, was beim Upload tatsächlich geprüft wird.
  const fpBanner = el("div", { class: "fp-banner loading" }, "🎧 Lade Fingerprint-Status …");
  panel.appendChild(fpBanner);
  fetch("/api/fingerprint/status").then(r => r.json()).then((s) => {
    if (!s.fpcalc_available) {
      fpBanner.className = "fp-banner off";
      fpBanner.textContent = "⚠ Fingerprint-Schutz ist inaktiv (fpcalc fehlt). Uploads werden NICHT geprüft.";
      return;
    }
    if (!s.acoustid_configured) {
      fpBanner.className = "fp-banner partial";
      fpBanner.textContent = "🎧 Fingerprint-Schutz aktiv — aber nur lokale Duplikat-Erkennung (kein AcoustID-Key).";
      return;
    }
    if (s.mode === "off") {
      fpBanner.className = "fp-banner partial";
      fpBanner.textContent = "🎧 Fingerprint-Schutz aktiv — AcoustID-Lookup deaktiviert (Modus „off“).";
      return;
    }
    fpBanner.className = "fp-banner ok";
    fpBanner.textContent = s.mode === "strict"
      ? "🎧 Fingerprint-Schutz aktiv: Uploads werden gegen ~80 Mio bekannte Songs geprüft. Bekannte Songs werden blockiert."
      : "🎧 Fingerprint-Schutz aktiv: AcoustID-Matches werden nur protokolliert (Modus „warn“).";
  }).catch(() => {
    fpBanner.className = "fp-banner off";
    fpBanner.textContent = "Fingerprint-Status nicht abrufbar.";
  });

  const cols = el("div", { class: "upload-cols" });

  // Einzelsong -> wird als Single angelegt
  const single = el("form", { class: "upload-box" });
  single.appendChild(el("h4", {}, "🎵 Einzelnen Song"));
  single.appendChild(el("div", { class: "field" }, el("label", {}, "Songtitel *"),
    el("input", { name: "title", required: true })));
  single.appendChild(el("div", { class: "field" }, el("label", {}, "Genre (frei erfinden!)"),
    el("input", { name: "genre", list: "genres-dl", placeholder: "z.B. Streik-Swing" }), genreDatalist()));
  single.appendChild(el("div", { class: "field" }, el("label", {}, "Jahr"),
    el("input", { name: "year", type: "number", value: new Date().getFullYear(), min: 1900, max: 2100 })));
  single.appendChild(el("div", { class: "field" }, el("label", {}, "Audiodatei (MP3) *"),
    el("input", { name: "audio", type: "file", required: true, accept: "audio/mpeg,.mp3" })));
  single.appendChild(el("div", { class: "field" }, el("label", {}, "Cover (optional)"),
    el("input", { name: "cover", type: "file", accept: "image/*" })));
  single.appendChild(el("button", { type: "submit", class: "primary-btn full" }, "Als Single veröffentlichen"));
  single.addEventListener("submit", (e) => { e.preventDefault(); doSingle(single); });

  // Bündel (Album/EP/Single) -> leeres Release, Songs danach hinzufügen
  const bundle = el("form", { class: "upload-box" });
  bundle.appendChild(el("h4", {}, "💿 Bündel (Album / EP / Single)"));
  bundle.appendChild(el("div", { class: "field" }, el("label", {}, "Titel *"),
    el("input", { name: "title", required: true })));
  bundle.appendChild(el("div", { class: "field-row" },
    el("div", { class: "field" }, el("label", {}, "Typ"),
      el("select", { name: "type" },
        el("option", { selected: true }, "Album"), el("option", {}, "EP"), el("option", {}, "Single"))),
    el("div", { class: "field" }, el("label", {}, "Jahr"),
      el("input", { name: "year", type: "number", value: new Date().getFullYear(), min: 1900, max: 2100 }))));
  bundle.appendChild(el("div", { class: "field" }, el("label", {}, "Genre (frei erfinden!)"),
    el("input", { name: "genre", list: "genres-dl", placeholder: "z.B. Allmende-Dub" }), genreDatalist()));
  bundle.appendChild(el("div", { class: "field" }, el("label", {}, "Cover (optional)"),
    el("input", { name: "cover", type: "file", accept: "image/*" })));
  bundle.appendChild(el("button", { type: "submit", class: "ghost-btn full" }, "Bündel anlegen"));
  bundle.appendChild(el("p", { class: "image-hint" }, "Danach unten Songs hinzufügen."));
  bundle.addEventListener("submit", (e) => { e.preventDefault(); doBundle(bundle); });

  cols.appendChild(single);
  cols.appendChild(bundle);
  panel.appendChild(cols);
  return panel;
}

/* ---- Bestehende Releases (editierbar) ---- */
function renderReleasesPanel(a) {
  const panel = el("div", { class: "panel" });
  panel.appendChild(el("h3", {}, `Deine Releases (${a.releases.length})`));
  if (!a.releases.length) {
    panel.appendChild(el("p", { class: "image-hint" }, "Noch nichts veröffentlicht. Nutze die Werkzeuge oben."));
  }
  a.releases.forEach((rel) => panel.appendChild(renderReleaseCard(rel)));
  return panel;
}

function renderReleaseCard(rel) {
  const card = el("form", { class: "release-card" });

  // Kopf: Cover + editierbare Felder
  const cover = el("div", { class: "release-cover-sm", style: `background:${colorOf(rel.id)}` });
  if (rel.coverThumb) cover.appendChild(el("img", { src: rel.coverThumb, alt: "" }));
  else cover.textContent = initials(rel.title);

  const head = el("div", { class: "release-card-head" }, cover,
    el("div", { class: "info release-edit-fields" },
      el("input", { name: "title", value: rel.title, class: "rel-title-input" }),
      el("div", { class: "field-row" },
        el("select", { name: "type" }, ...["Album", "EP", "Single"].map((t) =>
          el("option", t === rel.type ? { selected: true } : {}, t))),
        el("input", { name: "year", type: "number", value: rel.year, min: 1900, max: 2100, class: "rel-year-input" }),
        el("input", { name: "genre", value: rel.genre || "", list: "genres-dl", placeholder: "Genre", class: "rel-genre-input" }),
        genreDatalist(),
        el("label", { class: "cover-change" }, "Cover ändern",
          el("input", { name: "cover", type: "file", accept: "image/*", hidden: true })))),
    el("button", { type: "submit", class: "ghost-btn small" }, "Speichern"),
    el("button", { type: "button", class: "danger-btn", onclick: () => delRelease(rel) }, "Löschen"));
  card.appendChild(head);

  // Tracks
  rel.tracks.forEach((t, i) => {
    card.appendChild(el("div", { class: "studio-track" },
      el("span", { class: "idx" }, String(i + 1)),
      el("span", {}, t.title, t.trackGenre ? el("span", { class: "track-genre-badge" }, t.trackGenre) : null),
      el("span", { class: "dur" }, t.duration ? fmtTime(t.duration) : "–"),
      el("button", { type: "button", class: "del", title: "Song löschen",
        onclick: () => delTrack(t) }, "✕")));
  });

  card.addEventListener("submit", (e) => { e.preventDefault(); saveRelease(card, rel); });

  // Song zu diesem Release hinzufügen
  const tf = el("form", { class: "inline-form" });
  tf.appendChild(el("div", { class: "field", style: "flex:2" }, el("label", {}, "Songtitel *"),
    el("input", { name: "title", required: true, placeholder: "Songtitel" })));
  tf.appendChild(el("div", { class: "field" }, el("label", {}, "Genre (optional)"),
    el("input", { name: "genre", list: "genres-dl", placeholder: "erbt vom Release" }), genreDatalist()));
  tf.appendChild(el("div", { class: "field", style: "flex:2" }, el("label", {}, "Audiodatei (MP3) *"),
    el("input", { name: "audio", type: "file", required: true, accept: "audio/mpeg,.mp3" })));
  tf.appendChild(el("button", { type: "submit", class: "primary-btn small" }, "+ Song"));
  tf.addEventListener("submit", (e) => { e.preventDefault(); addTrack(tf, rel); });

  const wrap = el("div", {});
  wrap.appendChild(card);
  card.appendChild(tf);
  return wrap;
}

/* ---- Aktionen ---- */
async function refresh() {
  const me = await apiJson("/api/auth/me");
  if (me.authenticated && me.artist) { state.artist = me.artist; state.email = me.email; renderEditor(); }
}

async function showDeleteProfileDialog() {
  const msg = "Bist du sicher? Dies kann nicht rückgängig gemacht werden. Gib dein Passwort ein zum Löschen:";
  const password = prompt(msg);
  if (!password) return;

  try {
    const fd = new FormData();
    fd.set("password", password);
    const r = await fetch("/api/studio/artist", { method: "DELETE", body: fd });
    if (!r.ok) {
      const d = await r.json();
      toast("Fehler: " + (d.detail || "Löschen fehlgeschlagen"), "error");
      return;
    }
    toast("Profil gelöscht. Auf Wiedersehen!", "ok");
    setTimeout(() => location.href = "/", 1500);
  } catch (err) {
    toast("Fehler: " + err.message, "error");
  }
}

async function doSingle(form) {
  const fd = new FormData(form);
  if (!fd.get("cover")?.size) fd.delete("cover");
  await guard(form, () => apiSend("POST", "/api/studio/single", fd), "Single veröffentlicht.");
}
async function doBundle(form) {
  const fd = new FormData(form);
  if (!fd.get("cover")?.size) fd.delete("cover");
  await guard(form, () => apiSend("POST", "/api/studio/releases", fd), "Bündel angelegt.");
}
async function saveRelease(form, rel) {
  const fd = new FormData(form);
  if (!fd.get("cover")?.size) fd.delete("cover");
  await guard(form, () => apiSend("PUT", `/api/studio/releases/${rel.id}`, fd), "Release gespeichert.");
}
async function addTrack(form, rel) {
  const fd = new FormData(form);
  await guard(form, () => apiSend("POST", `/api/studio/releases/${rel.id}/tracks`, fd), "Song hinzugefügt.");
}
async function delRelease(rel) {
  if (!confirm(`Release „${rel.title}" wirklich löschen?`)) return;
  try { await apiSend("DELETE", `/api/studio/releases/${rel.id}`); toast("Gelöscht.", "ok"); await refresh(); }
  catch (err) { toast("Fehler: " + err.message, "error"); }
}
async function delTrack(t) {
  try { await apiSend("DELETE", `/api/studio/tracks/${t.id}`); toast("Song gelöscht.", "ok"); await refresh(); }
  catch (err) { toast("Fehler: " + err.message, "error"); }
}

async function guard(form, fn, okMsg) {
  const btn = $("button[type=submit]", form);
  try {
    if (btn) { btn.disabled = true; }
    const result = await fn();
    toast(okMsg, "ok");
    // Fingerprint-Resonanz: zeige in einem zweiten Toast, was geprüft wurde.
    if (result && result.fingerprint && result.fingerprint.note) {
      const kind = result.fingerprint.checked ? "ok" : "warn";
      setTimeout(() => toast(result.fingerprint.note, kind), 600);
    }
    await refresh();
  } catch (err) {
    toast("Fehler: " + err.message, "error");
    if (btn) btn.disabled = false;
  }
}

async function logout() {
  try { await apiSend("POST", "/api/auth/logout"); } catch {}
  state.artist = null; state.email = null;
  toast("Abgemeldet.", "ok");
  renderAuth("login");
}

/* ---- Start ---- */
(async function init() {
  try {
    state.genres = await apiJson("/api/genres");
    const me = await apiJson("/api/auth/me");
    if (me.authenticated && me.artist) {
      state.artist = me.artist; state.email = me.email;
      renderEditor();
    } else {
      renderAuth("login");
    }
  } catch (err) {
    toast("Backend nicht erreichbar: " + err.message, "error");
    renderAuth("login");
  }
})();
