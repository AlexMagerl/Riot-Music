/* Riot Music — gemeinsames Anti-Bot-Captcha für Registrierung, Admin-Bootstrap
   und Kontaktformular.

   Ist im Admin-Bereich Friendly Captcha eingerichtet, erscheint dessen Widget
   (rechnet im Hintergrund, keine Bilderrätsel). Sonst die eingebaute Mathe-Frage.
   Beide Varianten liefern dem Formular die Felder `captchaId` + `captchaAnswer`. */
(function () {
  "use strict";

  const FRC_SCRIPT = "https://cdn.jsdelivr.net/npm/@friendlycaptcha/sdk@1.1.1/site.min.js";
  const FRC_ID = "frc";
  let sdkPromise = null;

  function loadFriendlySdk() {
    if (window.frcaptcha) return Promise.resolve(window.frcaptcha);
    if (!sdkPromise) {
      sdkPromise = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.type = "module";
        s.src = FRC_SCRIPT;
        s.onerror = () => reject(new Error("script"));
        document.head.appendChild(s);
        const started = Date.now();
        (function waitForGlobal() {
          if (window.frcaptcha) return resolve(window.frcaptcha);
          if (Date.now() - started > 15000) return reject(new Error("timeout"));
          setTimeout(waitForGlobal, 100);
        })();
      });
      sdkPromise.catch(() => { sdkPromise = null; });
    }
    return sdkPromise;
  }

  function node(tag, attrs, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") e.className = v;
      else if (k === "style") e.style.cssText = v;
      else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    }
    for (const c of children) if (c != null) e.append(c);
    return e;
  }

  /**
   * Baut das Captcha-Feld. Rückgabe: { element, reload() }.
   * `reload()` nach jedem Absenden aufrufen – jede Antwort gilt nur einmal.
   */
  function mount(opts = {}) {
    const idInput = node("input", { type: "hidden", name: "captchaId" });
    const body = node("div", { class: "captcha-body" }, "lädt …");
    const element = node("div", { class: "field captcha-field" },
      node("label", {}, opts.label || "Anti-Bot-Prüfung"), body, idInput);

    let widget = null;
    let answerInput = null;

    function renderMath(challenge) {
      idInput.value = challenge.id;
      answerInput = node("input", { name: "captchaAnswer", required: "", inputmode: "numeric",
        autocomplete: "off", placeholder: "Antwort" });
      const reloadBtn = node("button", { type: "button", class: "ghost-btn small",
        onclick: (e) => { e.preventDefault(); reload(); } }, "↻ Neu");
      body.replaceChildren(node("div", { class: "captcha-row" },
        node("div", { class: "captcha-q" }, challenge.question), answerInput, reloadBtn));
    }

    async function renderFriendly(sitekey) {
      idInput.value = FRC_ID;
      answerInput = node("input", { type: "hidden", name: "captchaAnswer" });
      const holder = node("div", { class: "frc-captcha" });
      body.replaceChildren(holder, answerInput);
      try {
        const sdk = await loadFriendlySdk();
        widget = sdk.createWidget({ element: holder, sitekey });
        holder.addEventListener("frc:widget.complete", (e) => {
          answerInput.value = (e.detail && e.detail.response) || "";
        });
        holder.addEventListener("frc:widget.expire", () => { answerInput.value = ""; });
        holder.addEventListener("frc:widget.error", () => { answerInput.value = ""; });
      } catch {
        body.replaceChildren(node("div", { class: "captcha-q", style: "color:#ff6b6f" },
          "Die Anti-Bot-Prüfung konnte nicht geladen werden. " +
          "Bitte Werbeblocker für diese Seite deaktivieren und neu laden."), answerInput);
      }
    }

    async function reload() {
      if (widget) {
        // Friendly: gleiches Widget zurücksetzen, es löst dann neu.
        answerInput.value = "";
        widget.reset();
        return;
      }
      body.textContent = "lädt …";
      try {
        const c = await fetch("/api/auth/captcha").then((r) => r.json());
        if (c.provider === "friendly") await renderFriendly(c.sitekey);
        else renderMath(c);
      } catch {
        body.textContent = "Anti-Bot-Prüfung konnte nicht geladen werden.";
      }
    }

    reload();
    return { element, reload };
  }

  window.RiotCaptcha = { mount };
})();
