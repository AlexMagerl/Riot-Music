/* Riot Music — Konto-Sicherheit (Künstlerbereich und Admin gemeinsam).
   2FA-Code beim Login, Einrichtung per Authenticator-App (QR-Code),
   Wiederherstellungscodes, Passwort ändern/vergessen, überall abmelden.
   Eigenständig: bringt eigene kleine Helfer mit, nutzt vorhandene CSS-Klassen. */
(function () {
  "use strict";

  function h(tag, attrs, ...children) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "html") n.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      n.append(c);
    }
    return n;
  }

  async function api(method, url, data) {
    let body;
    if (data instanceof FormData) body = data;
    else if (data) { body = new FormData(); for (const [k, v] of Object.entries(data)) body.set(k, v); }
    const res = await fetch(url, { method, body });
    let json = null;
    try { json = await res.json(); } catch { /* leer */ }
    if (!res.ok) throw new Error((json && json.detail) || `Fehler ${res.status}`);
    return json;
  }

  function status() { return h("div", { class: "contact-status", style: "min-height:1.3em" }); }
  function setStatus(el, msg, kind) { el.className = "contact-status" + (kind ? " " + kind : ""); el.textContent = msg; }
  function field(label, input, hint) {
    return h("div", { class: "field" }, h("label", {}, label), input, hint ? h("div", { class: "image-hint" }, hint) : null);
  }
  const codeInput = (name = "code") => h("input", {
    name, required: true, autocomplete: "one-time-code", inputmode: "text",
    placeholder: "123456", class: "sec-code-input", maxlength: 16 });

  /* ------------------------------------------------------------------
     Login-Schritt 2: Code aus der App (oder Wiederherstellungscode)
     ------------------------------------------------------------------ */
  function mfaChallenge(container, { mfaToken, onSuccess, onCancel }) {
    const st = status();
    const input = codeInput();
    const remember = h("input", { type: "checkbox", name: "remember" });
    const form = h("form", { class: "auth-form" },
      field("Code aus deiner Authenticator-App", input,
        "Handy verloren? Gib stattdessen einen deiner Wiederherstellungscodes ein (z. B. abcde-fghij)."),
      h("label", { class: "agb-accept" }, remember, h("span", {}, "Dieses Gerät 30 Tage merken")),
      h("button", { type: "submit", class: "primary-btn full" }, "Bestätigen"),
      st);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      setStatus(st, "Prüfe …");
      try {
        const res = await api("POST", "/api/auth/mfa",
          { mfaToken, code: input.value.trim(), remember: remember.checked ? "on" : "" });
        if (typeof res.recoveryCodesLeft === "number") {
          alert(`Wiederherstellungscode verwendet. Du hast noch ${res.recoveryCodesLeft} übrig. ` +
                "Erzeuge im Bereich „Sicherheit“ neue, sobald du wieder Zugriff auf deine App hast.");
        }
        onSuccess(res);
      } catch (err) {
        setStatus(st, "✗ " + err.message, "error");
        btn.disabled = false;
        input.select();
        if (/abgelaufen/i.test(err.message) && onCancel) setTimeout(onCancel, 1800);
      }
    });
    container.replaceChildren(h("div", { class: "auth-card" },
      h("div", { class: "sec-big-ico" }, "🔐"),
      h("h1", {}, "Zwei-Faktor-Anmeldung"),
      h("p", { class: "auth-sub" }, "Öffne deine Authenticator-App und gib den aktuellen 6-stelligen Code ein."),
      form,
      onCancel ? h("div", { style: "margin-top:14px;text-align:center" },
        h("a", { href: "#", class: "back-link", onclick: (e) => { e.preventDefault(); onCancel(); } },
          "← Zurück zur Anmeldung")) : null));
    input.focus();
  }

  /* ------------------------------------------------------------------
     Wiederherstellungscodes anzeigen (nur einmal sichtbar!)
     ------------------------------------------------------------------ */
  function recoveryCodesView(codes, onDone) {
    const text = "Riot Music – Wiederherstellungscodes\n" +
      "Jeder Code funktioniert genau einmal, falls du keinen Zugriff auf deine Authenticator-App hast.\n\n" +
      codes.join("\n") + "\n";
    const confirm = h("input", { type: "checkbox" });
    const done = h("button", { type: "button", class: "primary-btn", disabled: true,
      onclick: () => onDone && onDone() }, "Fertig");
    confirm.addEventListener("change", () => { done.disabled = !confirm.checked; });
    const copied = status();
    return h("div", { class: "sec-recovery" },
      h("p", { class: "sec-warning" },
        "⚠ Speichere diese Codes jetzt an einem sicheren Ort (Passwortmanager, Ausdruck). " +
        "Sie werden nur dieses eine Mal angezeigt. Ohne App und ohne diese Codes kommst du nicht mehr in dein Konto."),
      h("div", { class: "sec-codes" }, codes.map((c) => h("code", {}, c))),
      h("div", { class: "btn-row" },
        h("button", { type: "button", class: "ghost-btn", onclick: () => {
          navigator.clipboard.writeText(text).then(
            () => setStatus(copied, "✓ Kopiert", "ok"),
            () => setStatus(copied, "Kopieren nicht möglich – bitte abschreiben.", "error"));
        } }, "Kopieren"),
        h("button", { type: "button", class: "ghost-btn", onclick: () => {
          const a = h("a", { href: URL.createObjectURL(new Blob([text], { type: "text/plain" })),
            download: "riot-music-wiederherstellungscodes.txt" });
          document.body.append(a); a.click(); a.remove();
        } }, "Als Datei speichern"),
        copied),
      h("label", { class: "agb-accept" }, confirm, h("span", {}, "Ich habe die Codes sicher gespeichert.")),
      h("div", { class: "btn-row" }, done));
  }

  /* ------------------------------------------------------------------
     2FA einrichten: QR-Code scannen → Code bestätigen → Codes sichern
     ------------------------------------------------------------------ */
  async function twoFactorSetup(container, { forced = false, onDone, onCancel } = {}) {
    container.replaceChildren(h("p", {}, "Lade …"));
    let setup;
    try { setup = await api("POST", "/api/account/2fa/setup"); }
    catch (err) { container.replaceChildren(h("p", { class: "contact-status error" }, "✗ " + err.message)); return; }

    let qr = null;
    try {
      const q = qrcode(0, "M"); q.addData(setup.uri); q.make();
      qr = h("div", { class: "qr-box sec-qr", html: q.createSvgTag(5, 2) });
    } catch { /* ohne QR: Schlüssel manuell eingeben */ }

    const st = status();
    const input = codeInput();
    const form = h("form", { class: "auth-form" },
      field("3. Code aus der App eingeben", input),
      h("div", { class: "btn-row" },
        h("button", { type: "submit", class: "primary-btn" }, "Aktivieren"),
        !forced && onCancel ? h("button", { type: "button", class: "ghost-btn", onclick: onCancel }, "Abbrechen") : null),
      st);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      setStatus(st, "Prüfe …");
      try {
        const res = await api("POST", "/api/account/2fa/enable", { code: input.value.trim() });
        container.replaceChildren(
          h("h3", {}, "✓ Zwei-Faktor-Anmeldung ist aktiv"),
          recoveryCodesView(res.recoveryCodes, onDone));
      } catch (err) { setStatus(st, "✗ " + err.message, "error"); input.select(); }
    });

    container.replaceChildren(
      forced ? h("p", { class: "sec-warning" },
        "Für den Admin-Bereich ist die Zwei-Faktor-Anmeldung Pflicht. Das dauert zwei Minuten.") : null,
      h("ol", { class: "sec-steps" },
        h("li", {}, "Installiere eine Authenticator-App, z. B. Aegis, 2FAS, Google Authenticator, Microsoft Authenticator oder nutze deinen Passwortmanager."),
        h("li", {}, "Scanne in der App diesen QR-Code:")),
      h("div", { class: "sec-qr-wrap" }, qr,
        h("div", { class: "image-hint" }, "QR-Code geht nicht? Schlüssel manuell eingeben:"),
        h("code", { class: "sec-secret" }, setup.secret.replace(/(.{4})/g, "$1 ").trim())),
      form);
    // Nicht zum Eingabefeld springen: Anleitung und QR-Code sollen zuerst sichtbar sein.
    input.focus({ preventScroll: true });
  }

  /* ------------------------------------------------------------------
     Passwort vergessen / neues Passwort setzen
     ------------------------------------------------------------------ */
  function forgotForm(container, { onBack } = {}) {
    const st = status();
    const form = h("form", { class: "auth-form" },
      field("E-Mail deines Kontos", h("input", { name: "email", type: "email", required: true, autocomplete: "email" })),
      h("div", { "aria-hidden": "true",
        style: "position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden;opacity:0" },
        h("input", { type: "text", name: "website", tabindex: "-1", autocomplete: "off" })));
    const captcha = window.RiotCaptcha ? RiotCaptcha.mount() : null;
    if (captcha) form.append(captcha.element);
    form.append(h("button", { type: "submit", class: "primary-btn full" }, "Link anfordern"), st);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      setStatus(st, "Sende …");
      try {
        const res = await api("POST", "/api/auth/forgot", new FormData(form));
        setStatus(st, res.mailEnabled
          ? "✓ Falls ein Konto mit dieser Adresse existiert, ist eine E-Mail mit einem Link unterwegs (auch im Spam-Ordner nachsehen)."
          : "E-Mail-Versand ist gerade nicht eingerichtet. Bitte melde dich über das Kontaktformular.", res.mailEnabled ? "ok" : "error");
        form.querySelector("button[type=submit]").disabled = true;
      } catch (err) {
        setStatus(st, "✗ " + err.message, "error");
        if (captcha) captcha.reload();
      }
    });
    container.replaceChildren(h("div", { class: "auth-card" },
      h("h1", {}, "Passwort vergessen"),
      h("p", { class: "auth-sub" }, "Wir schicken dir einen Link, mit dem du ein neues Passwort festlegen kannst."),
      form,
      onBack ? h("div", { style: "margin-top:14px;text-align:center" },
        h("a", { href: "#", class: "back-link", onclick: (e) => { e.preventDefault(); onBack(); } },
          "← Zurück zur Anmeldung")) : null));
  }

  function resetForm(container, token, { onDone } = {}) {
    const st = status();
    const pw1 = h("input", { type: "password", required: true, minlength: 8, autocomplete: "new-password" });
    const pw2 = h("input", { type: "password", required: true, minlength: 8, autocomplete: "new-password" });
    const form = h("form", { class: "auth-form" },
      field("Neues Passwort (mind. 8 Zeichen)", pw1),
      field("Wiederholen", pw2),
      h("button", { type: "submit", class: "primary-btn full" }, "Passwort speichern"), st);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (pw1.value !== pw2.value) { setStatus(st, "✗ Die Passwörter stimmen nicht überein.", "error"); return; }
      setStatus(st, "Speichere …");
      try {
        const res = await api("POST", "/api/auth/reset", { token, password: pw1.value });
        container.replaceChildren(h("div", { class: "auth-card" },
          h("div", { class: "sec-big-ico" }, "✅"),
          h("h1", {}, "Passwort geändert"),
          h("p", { class: "auth-sub" }, "Du kannst dich jetzt mit dem neuen Passwort anmelden. Alle anderen Geräte wurden abgemeldet."),
          h("button", { type: "button", class: "primary-btn full", onclick: () => onDone && onDone(res.role) }, "Zur Anmeldung")));
      } catch (err) { setStatus(st, "✗ " + err.message, "error"); }
    });
    container.replaceChildren(h("div", { class: "auth-card" },
      h("h1", {}, "Neues Passwort"),
      h("p", { class: "auth-sub" }, "Lege ein neues Passwort für dein Konto fest."),
      form));
    pw1.focus();
  }

  /* ------------------------------------------------------------------
     Bereich „Sicherheit“ im eingeloggten Zustand
     ------------------------------------------------------------------ */
  function securityPanel({ onLoggedOut } = {}) {
    const panel = h("div", { class: "panel sec-panel" }, h("h3", {}, "🔐 Sicherheit"), h("p", {}, "Lade …"));
    render();
    return panel;

    async function render() {
      let info;
      try { info = await api("GET", "/api/account/security"); }
      catch (err) { panel.replaceChildren(h("h3", {}, "🔐 Sicherheit"), h("p", { class: "contact-status error" }, err.message)); return; }

      const twoFa = h("div", { class: "sec-block" });
      renderTwoFa();
      panel.replaceChildren(h("h3", {}, "🔐 Sicherheit"), twoFa, passwordBlock(), sessionsBlock());

      function renderTwoFa() {
        if (!info.twoFactor) {
          twoFa.replaceChildren(
            h("h4", {}, "Zwei-Faktor-Anmeldung: ", h("span", { class: "sec-off" }, "aus")),
            h("p", { class: "image-hint" },
              "Schützt dein Konto, selbst wenn jemand dein Passwort kennt: Beim Login brauchst du zusätzlich einen Code aus einer App auf deinem Handy."),
            h("button", { type: "button", class: "primary-btn", onclick: () =>
              twoFactorSetup(twoFa, { onDone: refresh, onCancel: renderTwoFa }) }, "Jetzt einrichten"));
          return;
        }
        const st = status();
        const code = codeInput();
        const actions = h("div", { class: "btn-row" },
          h("button", { type: "button", class: "ghost-btn", onclick: async () => {
            if (!code.value.trim()) { setStatus(st, "Bitte zuerst einen aktuellen Code eingeben.", "error"); return; }
            try {
              const res = await api("POST", "/api/account/2fa/recovery-codes", { code: code.value.trim() });
              twoFa.replaceChildren(h("h4", {}, "Neue Wiederherstellungscodes"), recoveryCodesView(res.recoveryCodes, refresh));
            } catch (err) { setStatus(st, "✗ " + err.message, "error"); }
          } }, "Neue Wiederherstellungscodes"),
          info.twoFactorRequired ? null : h("button", { type: "button", class: "danger-btn", onclick: async () => {
            const pw = prompt("Zum Ausschalten bitte dein Passwort eingeben:");
            if (!pw) return;
            if (!code.value.trim()) { setStatus(st, "Bitte zusätzlich einen aktuellen Code eingeben.", "error"); return; }
            try { await api("POST", "/api/account/2fa/disable", { password: pw, code: code.value.trim() }); refresh(); }
            catch (err) { setStatus(st, "✗ " + err.message, "error"); }
          } }, "Ausschalten"));
        twoFa.replaceChildren(
          h("h4", {}, "Zwei-Faktor-Anmeldung: ", h("span", { class: "sec-on" }, "aktiv")),
          h("p", { class: "image-hint" },
            `Noch ${info.recoveryCodesLeft} Wiederherstellungscodes übrig.` +
            (info.twoFactorRequired ? " Für das Admin-Konto ist 2FA Pflicht." : "")),
          field("Aktueller Code (für die Aktionen unten)", code), actions, st);
      }
    }

    function refresh() { render(); }

    function passwordBlock() {
      const st = status();
      const cur = h("input", { type: "password", name: "currentPassword", required: true, autocomplete: "current-password" });
      const nw = h("input", { type: "password", name: "newPassword", required: true, minlength: 8, autocomplete: "new-password" });
      const form = h("form", { class: "sec-block" },
        h("h4", {}, "Passwort ändern"),
        field("Aktuelles Passwort", cur),
        field("Neues Passwort (mind. 8 Zeichen)", nw, "Alle anderen Geräte werden dabei abgemeldet."),
        h("button", { type: "submit", class: "primary-btn" }, "Passwort ändern"), st);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await api("POST", "/api/account/password", new FormData(form));
          form.reset();
          setStatus(st, "✓ Passwort geändert. Andere Geräte sind abgemeldet.", "ok");
        } catch (err) { setStatus(st, "✗ " + err.message, "error"); }
      });
      return form;
    }

    function sessionsBlock() {
      return h("div", { class: "sec-block" },
        h("h4", {}, "Überall abmelden"),
        h("p", { class: "image-hint" },
          "Beendet alle Anmeldungen auf allen Geräten – auch hier. Sinnvoll, wenn du dich auf einem fremden Gerät nicht abgemeldet hast."),
        h("button", { type: "button", class: "danger-btn", onclick: async () => {
          if (!confirm("Wirklich auf allen Geräten abmelden?")) return;
          try { await api("POST", "/api/account/logout-all"); } catch { /* egal */ }
          if (onLoggedOut) onLoggedOut(); else location.reload();
        } }, "Überall abmelden"));
    }
  }

  window.RiotSecurity = { mfaChallenge, twoFactorSetup, recoveryCodesView, forgotForm, resetForm, securityPanel };
})();
