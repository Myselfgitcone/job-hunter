// Job Hunter Autofill — content script.
// Scans a job-application page's form fields, asks the backend to answer them
// with the same engine the web app uses, then fills the DOM for review.
// Nothing is submitted — the user reviews and clicks the page's own submit.

(() => {
  if (window.__jhAutofillLoaded) return;
  window.__jhAutofillLoaded = true;

  const send = (type, payload) =>
    new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type, payload }, (res) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (res?.error) return reject(new Error(res.error));
        resolve(res?.data);
      });
    });

  // ── Field scanning ─────────────────────────────────────────────────────────
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();

  function labelFor(el) {
    // 1. <label for=id>
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return norm(l.textContent);
    }
    // 2. wrapping <label>
    const wrap = el.closest("label");
    if (wrap) {
      const clone = wrap.cloneNode(true);
      clone.querySelectorAll("input,select,textarea").forEach((n) => n.remove());
      const t = norm(clone.textContent);
      if (t) return t;
    }
    // 3. aria-label / aria-labelledby
    if (el.getAttribute("aria-label")) return norm(el.getAttribute("aria-label"));
    const ll = el.getAttribute("aria-labelledby");
    if (ll) {
      const parts = ll.split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean);
      const t = norm(parts.map((n) => n.textContent).join(" "));
      if (t) return t;
    }
    // 4. closest form-group label / legend / preceding text
    const grp = el.closest("[class*='field'],[class*='question'],[class*='form-group'],fieldset,div");
    if (grp) {
      const lab = grp.querySelector("label,legend,.label,[class*='label']");
      if (lab && !lab.contains(el)) {
        const t = norm(lab.textContent);
        if (t) return t;
      }
    }
    // 5. placeholder / name
    return norm(el.getAttribute("placeholder") || el.name || "");
  }

  function optionList(el) {
    if (el.tagName === "SELECT") {
      return [...el.options]
        .filter((o) => o.value !== "" && !/^\s*(select|choose|—|-)/i.test(o.textContent))
        .map((o) => ({ label: norm(o.textContent), value: o.value }));
    }
    return [];
  }

  const SKIP_TYPES = new Set(["hidden", "submit", "button", "reset", "image", "file", "password", "search"]);

  function scanFields() {
    const fields = [];
    const seenRadioName = new Set();
    let idx = 0;

    const els = [...document.querySelectorAll("input, select, textarea")];
    for (const el of els) {
      if (el.disabled || el.offsetParent === null) continue; // skip hidden/disabled
      const tag = el.tagName;
      const type = (el.type || "").toLowerCase();
      if (tag === "INPUT" && SKIP_TYPES.has(type)) continue;

      // Radio / checkbox groups — one field per name
      if (tag === "INPUT" && (type === "radio" || type === "checkbox")) {
        const name = el.name;
        if (!name || seenRadioName.has(name)) continue;
        seenRadioName.add(name);
        const group = els.filter((e) => e.tagName === "INPUT" && e.name === name && e.type === type);
        const options = group.map((g) => ({ label: labelFor(g) || g.value, value: g.value }));
        // group label = nearest fieldset legend / preceding label
        const fs = el.closest("fieldset");
        let glabel = fs ? norm(fs.querySelector("legend")?.textContent || "") : "";
        if (!glabel) {
          const grp = el.closest("[class*='field'],[class*='question'],[class*='form-group'],div");
          glabel = norm(grp?.querySelector("label,.label,[class*='label']")?.textContent || "");
        }
        const key = `f${idx++}`;
        fields.push({ el: group, isGroup: true, groupType: type, key,
          field: { key, label: glabel || name, type: type === "radio" ? "select" : "multiselect", options } });
        continue;
      }

      const label = labelFor(el);
      if (!label || label.length < 2) continue;
      const options = optionList(el);
      let ftype = "text";
      if (tag === "TEXTAREA") ftype = "textarea";
      else if (tag === "SELECT") ftype = "select";
      const key = `f${idx++}`;
      fields.push({ el, isGroup: false, key, field: { key, label, type: ftype, options } });
    }
    return fields;
  }

  // ── Filling ────────────────────────────────────────────────────────────────
  function setNativeValue(el, value) {
    const proto = el.tagName === "TEXTAREA"
      ? window.HTMLTextAreaElement.prototype
      : el.tagName === "SELECT"
        ? window.HTMLSelectElement.prototype
        : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function fillField(entry, value) {
    if (value === undefined || value === null || value === "") return false;
    const { field } = entry;
    if (entry.isGroup) {
      const wanted = Array.isArray(value) ? value.map(String) : [String(value)];
      let hit = false;
      for (const input of entry.el) {
        const match = wanted.includes(input.value) ||
          wanted.some((w) => norm(w).toLowerCase() === norm(labelFor(input)).toLowerCase());
        if (match && !input.checked) {
          input.click();
          hit = true;
          if (entry.groupType === "radio") break;
        }
      }
      return hit;
    }
    if (field.type === "select") {
      const opt = [...entry.el.options].find(
        (o) => o.value === String(value) ||
          norm(o.textContent).toLowerCase() === norm(String(value)).toLowerCase());
      if (opt) { setNativeValue(entry.el, opt.value); return true; }
      return false;
    }
    setNativeValue(entry.el, String(value));
    return true;
  }

  function outline(entry, ai) {
    const nodes = entry.isGroup ? entry.el : [entry.el];
    for (const n of nodes) {
      const target = n.closest("[class*='field'],[class*='question'],label,div") || n;
      target.classList.add(ai ? "jh-filled-ai" : "jh-filled");
      setTimeout(() => target.classList.remove("jh-filled", "jh-filled-ai"), 4000);
    }
  }

  // Read the CURRENT value the user has left in each field — used to learn
  // manual answers when they submit.
  function readValue(entry) {
    if (entry.isGroup) {
      const checked = entry.el.filter((i) => i.checked);
      if (!checked.length) return "";
      const labels = checked.map((i) => norm(labelFor(i)) || i.value);
      return entry.groupType === "radio" ? labels[0] : labels;
    }
    if (entry.field.type === "select") {
      const o = entry.el.selectedOptions?.[0];
      return o ? norm(o.textContent) : "";
    }
    return norm(entry.el.value || "");
  }

  // After a fill, remember the entries so a later submit can read final values.
  let lastEntries = null;
  async function learnFromPage() {
    if (!lastEntries) return;
    const values = {};
    for (const e of lastEntries) {
      const v = readValue(e);
      if (v !== "" && !(Array.isArray(v) && !v.length)) values[e.key] = v;
    }
    if (!Object.keys(values).length) return;
    try {
      await send("learn", { fields: lastEntries.map((e) => e.field), values });
    } catch { /* non-blocking */ }
  }

  // Fire learn when the user clicks a real submit control (their final
  // answers). Capture-phase so it runs before navigation; never blocks it.
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest?.(
      "button[type=submit], input[type=submit], [class*='submit'], [id*='submit']");
    if (t && lastEntries) learnFromPage();
  }, true);

  function pageMeta() {
    const h1 = norm(document.querySelector("h1")?.textContent || document.title);
    return { url: location.href, title: h1.slice(0, 120), company: norm(location.hostname.replace(/^www\./, "")) };
  }

  // ── Orchestration ────────────────────────────────────────────────────────────
  async function runFill(onStatus) {
    const entries = scanFields();
    if (!entries.length) { onStatus({ error: "No application form fields found on this page." }); return; }
    lastEntries = entries; // remembered so a later submit can learn manual edits
    onStatus({ scanning: entries.length });
    let data;
    try {
      data = await send("answer", {
        ...pageMeta(),
        fields: entries.map((e) => e.field),
        ai_fill: true,
      });
    } catch (e) {
      onStatus({ error: e.message });
      return;
    }
    const answers = data.answers || {};
    const aiKeys = new Set(data.ai_keys || []);
    let filled = 0, ai = 0;
    for (const entry of entries) {
      const v = answers[entry.key];
      if (fillField(entry, v)) {
        filled++;
        const isAi = aiKeys.has(entry.key);
        if (isAi) ai++;
        outline(entry, isAi);
      }
    }
    onStatus({ done: true, total: entries.length, filled, ai, resume: data.resume_source });
  }
  window.__jhRunFill = runFill;

  // ── Floating button ──────────────────────────────────────────────────────────
  function looksLikeApplication() {
    // Count meaningful fillable fields (skip hidden/submit/search).
    const fields = [...document.querySelectorAll("input, textarea, select")].filter((el) => {
      const t = (el.type || "").toLowerCase();
      return el.tagName !== "INPUT" || !SKIP_TYPES.has(t);
    });
    return fields.length >= 3;
  }

  const isTop = window.top === window;

  // Auto-fill trigger: the app opens the ATS with a #jh=1 hash. That arms the
  // whole TAB in the background (via send('armTab')) so the trigger survives
  // the posting→form navigation, where the hash would be lost. Every top-frame
  // load asks the background whether its tab is armed, then auto-fills once the
  // form appears and disarms.
  let armAutofill = false;
  let autofillDone = false;
  let childHasForm = false;
  if (isTop) {
    if (/(?:^|[#&])jh=1(?:&|$)/.test(location.hash || "")) {
      try {
        const cleaned = location.href.replace(/([#&])jh=1(&|$)/, (_m, p, s) => (s === "&" ? p : "")).replace(/#$/, "");
        history.replaceState(null, "", cleaned);
      } catch { /* ignore */ }
      send("armTab", {}).catch(() => {});
      armAutofill = true;
    }
    // Also consult the background: a prior navigation in this tab may have armed it.
    send("isArmed", {}).then((r) => { if (r?.armed) { armAutofill = true; maybeAutofill(); } }).catch(() => {});
  }

  async function maybeAutofill() {
    if (!isTop || !armAutofill || autofillDone) return;
    const here = looksLikeApplication();
    if (!here && !childHasForm) return; // no form yet — wait for render
    autofillDone = true;
    send("disarmTab", {}).catch(() => {}); // one-shot — don't refill on later loads
    toast("Auto-filling from Job Hunter…");
    const handle = (s) => {
      if (!s || s.error) toast((s && s.error) || "No form fields found — sign in to the extension?", true);
      else if (s.done) toast(`Filled ${s.filled}/${s.total}${s.ai ? ` · ${s.ai} by AI` : ""} — review before submitting`);
    };
    if (here) await runFill(handle);
    else handle(await send("relayFill", {}));
  }

  // The button is ALWAYS hosted in the top frame (fixed to the real window,
  // so it never scrolls away). A form in a child iframe registers with the
  // background, which tells the top frame to show the button; the click is
  // relayed back to the form frame.
  function mountButton() {
    if (!isTop) return;
    if (document.getElementById("jh-fab")) return;
    const fab = document.createElement("button");
    fab.id = "jh-fab";
    fab.title = "Fill this application with Job Hunter";
    fab.innerHTML = `<span class="jh-fab-ico">⚡</span><span class="jh-fab-txt">Fill with Job Hunter</span>`;
    const busy = (on) => {
      fab.classList.toggle("jh-loading", on);
      fab.querySelector(".jh-fab-txt").textContent = on ? "Filling…" : "Fill with Job Hunter";
    };
    fab.addEventListener("click", async () => {
      busy(true);
      const handle = (s) => {
        if (!s || s.error) toast((s && s.error) || "No form fields found on this page.", true);
        else if (s.done) toast(`Filled ${s.filled}/${s.total}${s.ai ? ` · ${s.ai} by AI` : ""} — review before submitting`);
      };
      if (looksLikeApplication()) {
        await runFill(handle);           // form is in this (top) frame
      } else {
        const s = await send("relayFill", {}); // form is in a child frame
        handle(s);
      }
      busy(false);
    });
    document.body.appendChild(fab);
  }

  function unmountButton() {
    document.getElementById("jh-fab")?.remove();
  }

  // Report to the background whether THIS frame currently has a form.
  let lastHas = null;
  function reportForm() {
    const has = looksLikeApplication();
    if (has === lastHas) return;
    lastHas = has;
    send("registerForm", { has }).catch(() => {});
  }

  function toast(msg, err) {
    const t = document.createElement("div");
    t.className = "jh-toast" + (err ? " jh-toast-err" : "");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.classList.add("jh-show"), 10);
    setTimeout(() => { t.classList.remove("jh-show"); setTimeout(() => t.remove(), 300); }, 5000);
  }

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    // Background asks the top frame to show/hide the button (a child frame
    // has/lost a form).
    if (msg?.type === "showButton") {
      if (isTop) {
        childHasForm = !!msg.show;
        if (msg.show) { mountButton(); maybeAutofill(); }
        else if (!looksLikeApplication()) unmountButton();
      }
      sendResponse({ ok: true });
      return true;
    }
    // Direct fill request (popup, or background relay to the form frame).
    if (msg?.type === "fillPage") {
      if (!looksLikeApplication()) return false; // not the form frame — stay silent
      runFill((s) => sendResponse(s));
      return true;
    }
  });

  // React to dynamically-loaded ATS forms: re-check this frame, and if the
  // top frame itself has the form, mount directly.
  let raf = 0;
  const obs = new MutationObserver(() => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      reportForm();
      if (isTop && looksLikeApplication()) { mountButton(); maybeAutofill(); }
    });
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });
  reportForm();
  if (isTop && looksLikeApplication()) { mountButton(); maybeAutofill(); }
})();
