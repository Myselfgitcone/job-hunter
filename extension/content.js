// Job Hunter Autofill — content script.
// Scans a job-application page's form fields, asks the backend to answer them
// with the same engine the web app uses, then fills the DOM for review.
// Nothing is submitted — the user reviews and clicks the page's own submit.

(() => {
  if (window.__jhAutofillLoaded) return;
  window.__jhAutofillLoaded = true;

  // MV3's service worker can restart mid-call, and Chrome then silently never
  // fires the sendMessage callback ("message channel closed" in the console) —
  // the whole fill used to hang forever on that. Timeout + one retry: a fresh
  // sendMessage wakes the worker, and a real failure surfaces as an error
  // toast instead of a stuck "Filling…" button.
  const send = (type, payload) =>
    new Promise((resolve, reject) => {
      const timeoutMs = type === "answer" ? 90000 : 25000;
      let settled = false;
      const attempt = (retriesLeft) => {
        const timer = setTimeout(() => {
          if (settled) return;
          if (retriesLeft > 0) return attempt(retriesLeft - 1);
          settled = true;
          reject(new Error("Job Hunter background timed out — reload the page and try again."));
        }, timeoutMs);
        chrome.runtime.sendMessage({ type, payload }, (res) => {
          clearTimeout(timer);
          if (settled) return;
          if (chrome.runtime.lastError) {
            if (retriesLeft > 0) return attempt(retriesLeft - 1);
            settled = true;
            return reject(new Error(chrome.runtime.lastError.message));
          }
          settled = true;
          if (res?.error) return reject(new Error(res.error));
          resolve(res?.data);
        });
      };
      attempt(1);
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

  // Visibility that survives real ATS markup. offsetParent is null inside
  // position:fixed containers (Workday panels) and for visually-hidden
  // radio/checkbox inputs that ARE interactive via their visible label —
  // both were being skipped wholesale, which is why "it only fills a few".
  function isVisible(el) {
    if (el.getClientRects().length > 0) return true;
    const t = (el.type || "").toLowerCase();
    if (t === "radio" || t === "checkbox") {
      const lab = el.closest("label") ||
        (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`));
      return !!(lab && lab.getClientRects().length > 0);
    }
    return false;
  }

  // Anti-bot honeypot fields (Workday's "beecatcher"/website, generic traps).
  // Filling these flags the applicant as a bot → the whole submit is rejected.
  function isHoneypot(el) {
    const name = (el.name || "").toLowerCase();
    const aid = (el.getAttribute("data-automation-id") || "").toLowerCase();
    if (name === "website" || aid === "beecatcher") return true;
    // Off-screen / zero-size text traps that look normal in the DOM.
    const r = el.getBoundingClientRect();
    if ((r.width < 2 || r.height < 2) && el.tagName === "INPUT") return true;
    return false;
  }

  // Custom dropdowns that are NOT native <select>: Workday button dropdowns
  // (button[aria-haspopup=listbox]), ARIA comboboxes, react-select controls.
  // Options live in a popup that only exists once opened, so we scan them with
  // options:[] and resolve the choice at fill time (see fillCustomSelect).
  function isCustomSelectTrigger(el) {
    if (el.getAttribute("aria-haspopup") === "listbox") return true;
    if (el.getAttribute("role") === "combobox") return true;
    if (el.getAttribute("data-automation-id") === "multiSelectContainer") return true;
    const cls = el.className && el.className.baseVal !== undefined ? "" : (el.className || "");
    if (/select__control/.test(cls)) return true;
    return false;
  }

  function customSelectLabel(el) {
    const fc = el.closest("[data-automation-id^='formField-'],[class*='field'],[class*='question'],fieldset,div");
    if (fc) {
      const lab = fc.querySelector("label,legend,[id*='label']");
      if (lab && !lab.contains(el)) {
        const t = norm(lab.textContent);
        if (t) return t;
      }
    }
    return labelFor(el);
  }

  function scanFields() {
    const fields = [];
    const seenRadioName = new Set();
    const consumed = new WeakSet(); // custom-select inner inputs already handled
    let idx = 0;

    // ── Custom dropdowns first (Workday/react-select/ARIA) ──────────────────
    const customTriggers = [...document.querySelectorAll(
      "button[aria-haspopup='listbox'], [role='combobox'], [class*='select__control'], [data-automation-id='multiSelectContainer']"
    )];
    const seenCustom = new Set();
    for (const el of customTriggers) {
      if (el.disabled || !isVisible(el)) continue;
      if (!isCustomSelectTrigger(el)) continue;
      // Dedup nested matches (a multiSelectContainer also contains a listbox).
      const fcWrap = el.closest("[data-automation-id^='formField-']") || el;
      if (seenCustom.has(fcWrap)) continue;
      seenCustom.add(fcWrap);
      // multiselect-search = has a Search input; button-dropdown = doesn't.
      const isMulti = el.getAttribute("data-automation-id") === "multiSelectContainer" ||
                      !!el.querySelector?.("input[type='text']");
      // Mark any inner input so the native pass below doesn't double-capture it.
      el.querySelectorAll?.("input,textarea").forEach((n) => consumed.add(n));
      const label = customSelectLabel(el);
      if (!label || label.length < 2) continue;
      const key = `f${idx++}`;
      fields.push({ el, isCustomSelect: true, msSearch: isMulti, key,
        field: { key, label, type: "select", options: [] } });
    }

    const els = [...document.querySelectorAll("input, select, textarea")];
    for (const el of els) {
      if (el.disabled || !isVisible(el)) continue; // skip hidden/disabled
      if (consumed.has(el)) continue;                        // inner input of a custom select
      if (isHoneypot(el)) continue;                          // anti-bot trap — never fill
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
      else if (type === "date") ftype = "date";
      const key = `f${idx++}`;
      fields.push({ el, isGroup: false, key, field: { key, label, type: ftype, options } });
    }
    // Fill in PAGE ORDER, top to bottom — the two scanning passes (custom
    // dropdowns first, then natives) otherwise make the fill visibly start
    // mid-form and jump around.
    const nodeOf = (e) => (e.isGroup ? e.el[0] : e.el);
    fields.sort((a, b) => {
      const pa = nodeOf(a), pb = nodeOf(b);
      if (pa === pb) return 0;
      return (pa.compareDocumentPosition(pb) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1;
    });
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

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Full pointer event sequence — bare .click() registers a value on Workday
  // but can desync its framework; the real sequence keeps it stable. Proven
  // live on Workday's button dropdowns.
  function realClick(el) {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
      el.dispatchEvent(new MouseEvent(type,
        { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
    }
  }

  // Fold common name variants so "Saint Louis University" matches the list's
  // "St. Louis University" and vice versa.
  function foldName(s) {
    return norm(String(s)).toLowerCase()
      .replace(/\bst\.?\b/g, "saint")
      .replace(/\bunited states of america\b/g, "united states")
      .replace(/\busa\b/g, "united states");
  }

  // Token-set match so "United States" ~ "United States of America", and the
  // AI's phrasing matches an option without being identical.
  function optMatches(optText, want) {
    const a = foldName(optText);
    const b = foldName(want);
    if (!a || !b) return false;
    if (a === b || a.includes(b) || b.includes(a)) return true;
    const bt = b.split(/\W+/).filter((w) => w.length > 2);
    return bt.length > 0 && bt.every((w) => a.includes(w));
  }

  // Overlap score 0..1: fraction of `want`'s meaningful tokens found in the
  // option. Lets us take the BEST option when nothing matches perfectly.
  function optScore(optText, want) {
    const a = foldName(optText);
    const bt = foldName(want).split(/\W+/).filter((w) => w.length > 2);
    if (!bt.length) return 0;
    return bt.filter((w) => a.includes(w)).length / bt.length;
  }

  // Close any open dropdown popup. CRITICAL for sequential fields: leaving one
  // popup open makes the next dropdown's options ambiguous (a global
  // [role=option] query then sees the stale popup too), so every field after
  // an unmatched one silently fails. Escape is what Workday listens for.
  async function closeAnyPopup() {
    if (!document.querySelector("[role='option']")) return;
    try { document.activeElement?.blur?.(); } catch { /* ignore */ }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", keyCode: 27, bubbles: true }));
    try { document.body.click(); } catch { /* ignore */ }
    await sleep(250);
  }

  // Open a custom dropdown, click the option matching `value`, verify it stuck.
  // Guarantees the popup is closed on every exit path so the next field is clean.
  async function fillCustomSelect(trigger, value) {
    if (value === undefined || value === null || value === "") return false;
    await closeAnyPopup();                  // start from a clean slate
    try { trigger.focus(); } catch { /* ignore */ }
    realClick(trigger);
    await sleep(550);                       // popup renders in a portal
    const visibleOpts = () =>
      [...document.querySelectorAll("[role='option'], [class*='select__option']")]
        .filter((o) => o.getClientRects().length > 0 && norm(o.textContent) &&
                       !/^select one$/i.test(norm(o.textContent)));
    let opts = visibleOpts();
    let opt = opts.find((o) => optMatches(o.textContent, value));
    // Async type-to-search combobox (Greenhouse Country/School/Degree…):
    // options only exist after per-key typing. The trigger itself is the
    // input, or wraps one — type the value and re-scan; if the exact text
    // finds nothing (list spells it differently), retry with the value's most
    // distinctive word and take the best-scoring option.
    if (!opt) {
      const inner = trigger.tagName === "INPUT"
        ? trigger
        : trigger.querySelector?.("input:not([type='hidden'])");
      if (inner) {
        try { inner.focus(); } catch { /* ignore */ }
        const queries = [String(value)];
        const dw = distinctiveWord(value);
        if (dw && dw !== foldName(value)) queries.push(dw);
        for (const q of queries) {
          await typeSearch(inner, q);
          for (let tries = 0; tries < 10; tries++) {
            await sleep(320);
            opts = visibleOpts();
            if (opts.length) break;
          }
          if (!opts.length) continue;
          // Rank ALL matching options — first-match took "Maryville
          // University of St. Louis" over the exact "St. Louis University"
          // in live testing purely because of list order.
          const wantFold = foldName(value);
          const cands = opts.filter((o) => optMatches(o.textContent, value));
          opt = cands.find((o) => foldName(o.textContent) === wantFold);
          if (!opt && cands.length) {
            // Prefer the candidate that adds NO extra distinguishing words —
            // "St. Louis University" over "University of Missouri - St.
            // Louis". A candidate with extra proper nouns is a different
            // entity; picking it is worse than leaving the field blank.
            const wantToks = new Set(wantFold.split(/\W+/).filter(Boolean));
            const clean = cands.filter((o) =>
              foldName(o.textContent).split(/\W+/).filter(Boolean)
                .every((w) => wantToks.has(w) || _GENERIC_WORDS.has(w) || w.length <= 3));
            opt = clean[0] || null;
          }
          if (!opt) {
            // No token-subset match: best-overlap wins ONLY when it contains
            // the value's distinctive word — generic-word overlap alone
            // picked "Saint-Petersburg State University" for "Saint Louis
            // University" in live testing.
            const mustHave = distinctiveWord(value);
            const scored = opts
              .filter((o) => !mustHave || foldName(o.textContent).includes(mustHave))
              .map((o) => ({ o, s: optScore(o.textContent, value) }))
              .sort((a, b) => b.s - a.s);
            if (scored[0] && scored[0].s >= 0.75) opt = scored[0].o;
          }
          if (opt) break;
        }
      }
    }
    if (!opts.length && !opt) { await closeAnyPopup(); return false; }
    // Cascading categories ("Job Board ›", "Company Website ›"): open the
    // best category, then re-scan for the real option inside it.
    if (!opt && opts.length) {
      const isHeard = /hear about|source|referr/i.test(customSelectLabel(trigger));
      const cat = opts.find((o) => /[›>]\s*$/.test(norm(o.textContent)) &&
        (optMatches(o.textContent.replace(/[›>]/g, ""), value) ||
         (isHeard && /career|company|website|job\s*board|online/i.test(o.textContent))));
      if (cat) {
        realClick(cat);
        await sleep(500);
        opts = visibleOpts();
        opt = opts.find((o) => optMatches(o.textContent, value));
        if (!opt && isHeard) {
          opt = opts.find((o) => /career\s*(site|page)?|company\s*(career|web)?site|website/i.test(o.textContent));
        }
      }
    }
    // No confident match: only auto-pick a generic "how did you hear" bucket,
    // never guess an eligibility answer.
    if (!opt && /hear about|source|referr/i.test(customSelectLabel(trigger))) {
      opt = opts.find((o) => /other|job\s*board|website|online|career/i.test(o.textContent));
    }
    if (!opt) { await closeAnyPopup(); return false; }
    realClick(opt);
    await sleep(400);
    const ok = optMatches(trigger.textContent, value) || !/^select one$/i.test(norm(trigger.textContent));
    await closeAnyPopup();                  // ensure closed before the next field
    return ok;
  }

  // Type into a search/text input the React-safe way, WITHOUT firing blur
  // (blur would close the dropdown popup we're about to pick from).
  function typeInto(el, text) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    if (setter) setter.call(el, text); else el.value = text;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
  }

  // Char-by-char typing — async search comboboxes (Greenhouse School/City)
  // only fire their remote lookup on real per-key input events; a one-shot
  // value set leaves the menu at "No options" forever. Proven live.
  async function typeSearch(el, text) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    if (setter) setter.call(el, ""); else el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(150);
    for (const ch of String(text)) {
      const code = ch.charCodeAt(0);
      el.dispatchEvent(new KeyboardEvent("keydown", { key: ch, keyCode: code, which: code, bubbles: true }));
      if (setter) setter.call(el, el.value + ch); else el.value += ch;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: ch, keyCode: code, which: code, bubbles: true }));
      await sleep(45);
    }
  }

  // The most distinctive word of a value — retry query when the full text
  // finds nothing ("Saint Louis University" → "louis" surfaces the list's
  // "St. Louis University" spelling).
  const _GENERIC_WORDS = new Set(["university", "college", "institute", "school",
    "state", "the", "and", "united", "states", "city", "north", "south",
    "saint", "tech", "technical", "national", "international", "central"]);
  function distinctiveWord(value) {
    const words = foldName(value).split(/\W+/)
      .filter((w) => w.length > 3 && !_GENERIC_WORDS.has(w));
    words.sort((a, b) => b.length - a.length);
    return words[0] || "";
  }

  // Workday multiselect-search (chip + "Search" box + cascading options):
  // open → type the value → click the matching option. Handles the cascading
  // "How Did You Hear About Us?" (Job Board › / Social Media › …) since typing
  // a leaf term (e.g. "LinkedIn") surfaces it across categories.
  async function fillMultiSelectSearch(container, value) {
    if (value === undefined || value === null || value === "") return false;
    await closeAnyPopup();
    // Open first — the Search box renders lazily once the widget is expanded.
    const opener = container.querySelector("[data-automation-id='multiselectInputContainer']") || container;
    realClick(opener);
    await sleep(450);
    const search = container.querySelector("input[type='text']")
                || document.querySelector("input[placeholder='Search']");
    if (search) {
      try { search.focus(); } catch { /* ignore */ }
      typeInto(search, String(value));
    }
    await sleep(700);
    const visibleOpts = () => [...document.querySelectorAll("[role='option']")]
      .filter((o) => o.offsetParent !== null && norm(o.textContent) &&
                     !/^select one$/i.test(norm(o.textContent)));
    let opts = visibleOpts();
    let opt = opts.find((o) => optMatches(o.textContent, value));
    // Cascading: nothing matched but category rows exist — open the best
    // category (e.g. "Social Media ›"), then re-scan for the leaf.
    if (!opt && opts.length) {
      const cat = opts.find((o) => /›|>/.test(o.textContent) &&
        optMatches(o.textContent.replace(/[›>]/g, ""), value));
      if (cat) { realClick(cat); await sleep(500); opt = visibleOpts().find((o) => optMatches(o.textContent, value)); }
    }
    // "How did you hear" with no match → a safe generic leaf.
    if (!opt && /hear about|source|referr/i.test(customSelectLabel(container))) {
      opt = opts.find((o) => /other|job\s*board|website|online|social/i.test(o.textContent));
    }
    if (!opt) { await closeAnyPopup(); return false; }
    realClick(opt);
    await sleep(400);
    await closeAnyPopup();
    return true;
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
    if (entry.isCustomSelect) {
      // A committed react-select keeps its INPUT empty and renders the choice
      // in a single-value/multi-value chip — read the chip first, else the
      // trigger. (Reading only textContent counted every committed dropdown
      // as "required field still empty" and blocked the submit bar.)
      const el = entry.el;
      const box = el.closest("[class*='select__control']")?.parentElement
                || el.parentElement || el;
      const chip = box.querySelector("[class*='single-value'], [class*='multi-value']");
      if (chip) return norm(chip.textContent);
      const t = norm(el.value || el.textContent);
      return /^select( one)?(\.\.\.)?$/i.test(t) ? "" : t;
    }
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

  // ── Resume attachment ──────────────────────────────────────────────────────
  // Most ATS hide the real <input type=file> behind a styled "Attach" button, so
  // we deliberately do NOT skip invisible inputs here (unlike scanFields) — a
  // hidden input is still settable via DataTransfer.

  const COVER_RE = /cover\s*-?\s*letter|covering\s+letter/i;
  const RESUME_RE = /resum[eé]|\bcv\b|curriculum\s*vitae/i;
  // Uploads that are NOT the resume — never attach the resume to these.
  const OTHER_DOC_RE = /transcript|portfolio|photo|headshot|certificat|licen[sc]e|passport|visa\s*doc|work\s*sample|writing\s*sample|reference/i;

  function fileInputContext(el) {
    // Everything textual around the input that hints at what it wants.
    const bits = [el.name, el.id, el.getAttribute("aria-label"), el.getAttribute("accept"), labelFor(el)];
    const box = el.closest("[class*='field'],[class*='question'],[class*='upload'],[class*='attach'],fieldset,div");
    if (box) bits.push(norm(box.textContent).slice(0, 300));
    return norm(bits.filter(Boolean).join(" ")).toLowerCase();
  }

  function findResumeInput() {
    const inputs = [...document.querySelectorAll("input[type=file]")].filter((el) => !el.disabled);
    if (!inputs.length) return null;
    const scored = inputs.map((el) => {
      const ctx = fileInputContext(el);
      let score = 0;
      if (RESUME_RE.test(ctx)) score += 10;
      if (COVER_RE.test(ctx)) score -= 8;         // that's the cover-letter slot
      if (OTHER_DOC_RE.test(ctx)) score -= 10;    // transcript/portfolio/etc.
      if (el.required) score += 2;
      return { el, score, ctx };
    });
    scored.sort((a, b) => b.score - a.score);
    const best = scored[0];
    if (best.score > 0) return best.el;
    // No keyword anywhere: a lone, non-disqualified upload on an application
    // page is the resume in practice.
    if (inputs.length === 1 && best.score >= 0) return best.el;
    return null;
  }

  function setFile(input, file) {
    try {
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return input.files && input.files.length > 0;
    } catch {
      return false;
    }
  }

  // -> { state, filename, source } where state is
  // "attached" | "manual" (custom uploader / no input) | "none" | "error"
  // and source is "tailored" | "base" — surfaced in the UI so the user can
  // SEE which resume went on, instead of trusting that it was the right one.
  async function attachResume(meta) {
    const input = findResumeInput();
    if (!input) {
      // A drag-drop / Dropbox-style widget with no real file input — the user
      // must attach it; JS can't fill those.
      const hasUploadUi = /attach|upload|drag.{0,10}drop|dropbox|google drive/i
        .test(norm(document.body.innerText).slice(0, 20000));
      return { state: hasUploadUi ? "manual" : "none" };
    }
    if (input.files && input.files.length) {
      return { state: "attached", filename: input.files[0].name, source: "existing" };
    }
    try {
      const data = await send("resumeFile", meta);
      if (!data || !data.b64) return { state: "error" };
      const bin = atob(data.b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const file = new File([bytes], data.filename || "resume.pdf",
        { type: data.mime || "application/pdf" });
      if (!setFile(input, file)) return { state: "manual" };
      const target = input.closest("[class*='field'],[class*='upload'],[class*='attach'],div") || input;
      target.classList.add("jh-filled");
      setTimeout(() => target.classList.remove("jh-filled"), 4000);
      // Print the attached resume's FULL text to the console — open DevTools
      // (F12) to read exactly what is being submitted, not just its filename.
      try {
        const mj = data.matched_job || {};
        console.log(
          `%c[Job Hunter] Attached ${data.source === "base" ? "BASE" : "TAILORED"} resume: ` +
          `${data.filename || ""}${mj.company ? ` — matched job: ${mj.title || ""} @ ${mj.company}` : ""}`,
          `color:${data.source === "base" ? "#f59e0b" : "#10b981"};font-weight:bold`);
        console.log(data.text || "(no text returned)");
        window.jhResumeText = data.text || "";   // type jhResumeText to re-read it
      } catch { /* console unavailable */ }
      return { state: "attached", filename: data.filename || "resume.pdf",
               source: data.source || "" };
    } catch {
      return { state: "error" };
    }
  }

  // ── Submit (confirm-gated) ──────────────────────────────────────────────────
  // Nothing here EVER clicks submit on its own. After a fill we surface a
  // confirm bar; the actual submit fires only when the user presses "Submit".
  const SUBMIT_TEXT_RE = /\b(submit\s+application|submit|apply\s+now|send\s+application|finish|complete)\b/i;
  const SUBMIT_SKIP_RE = /\b(save|draft|cancel|back|previous|add|upload|attach|sign\s*in|log\s*in)\b/i;

  function findSubmitButton() {
    const cands = [
      ...document.querySelectorAll(
        "button[type=submit], input[type=submit], button, [role=button], a[class*='submit'], a[class*='apply']"
      ),
    ].filter((el) => el.offsetParent !== null && !el.disabled);
    let best = null, bestScore = 0;
    for (const el of cands) {
      const txt = norm(el.textContent || el.value || el.getAttribute("aria-label") || "");
      if (!txt || SUBMIT_SKIP_RE.test(txt)) continue;
      if (!SUBMIT_TEXT_RE.test(txt)) continue;
      let score = 1;
      if ((el.type || "").toLowerCase() === "submit") score += 3;
      if (/submit\s+application|send\s+application/i.test(txt)) score += 3;
      else if (/^submit$/i.test(txt)) score += 2;
      if (score > bestScore) { bestScore = score; best = el; }
    }
    return best;
  }

  // Required, still-empty fields — block submit and point the user at them.
  function unfilledRequired(entries) {
    const missing = [];
    for (const e of entries) {
      const nodes = e.isGroup ? e.el : [e.el];
      const req = nodes.some((n) => n.required || n.getAttribute("aria-required") === "true");
      if (!req) continue;
      const v = readValue(e);
      if (v === "" || (Array.isArray(v) && !v.length)) missing.push(e);
    }
    return missing;
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function submitBar(entries, submitBtn, summary, resumeInfo) {
    document.getElementById("jh-submit-bar")?.remove();
    const bar = document.createElement("div");
    bar.id = "jh-submit-bar";
    bar.className = "jh-submit-bar";
    const missing = unfilledRequired(entries);
    const warn = missing.length
      ? `<div class="jh-sb-warn">⚠ ${missing.length} required field(s) still empty — fill them first.</div>` : "";
    // Name the exact file that went on, and whether it is THIS job's tailored
    // resume or the generic base one — visible before every submit.
    const ri = resumeInfo || {};
    let resumeLine = "";
    if (ri.state === "attached" && ri.source === "base") {
      resumeLine = `<div class="jh-sb-resume jh-sb-base">⚠ BASE resume — not tailored for this job` +
        `<span>${esc(ri.filename || "")}</span></div>`;
    } else if (ri.state === "attached") {
      resumeLine = `<div class="jh-sb-resume jh-sb-tailored">✓ Tailored resume attached` +
        `<span>${esc(ri.filename || "")}</span></div>`;
    } else if (ri.state === "manual") {
      resumeLine = `<div class="jh-sb-resume jh-sb-base">⚠ Attach your resume manually (custom uploader)</div>`;
    } else if (ri.state === "error") {
      resumeLine = `<div class="jh-sb-resume jh-sb-base">⚠ Resume attach failed — tailor this job first</div>`;
    }
    bar.innerHTML =
      `<div class="jh-sb-msg">${summary}</div>${resumeLine}${warn}` +
      `<div class="jh-sb-actions">` +
      `<button class="jh-sb-cancel">Not yet</button>` +
      `<button class="jh-sb-go"${missing.length ? " disabled" : ""}>Submit application</button>` +
      `</div>`;
    document.body.appendChild(bar);
    bar.querySelector(".jh-sb-cancel").addEventListener("click", () => bar.remove());
    const go = bar.querySelector(".jh-sb-go");
    if (missing.length) {
      // Let the user jump to the first missing field.
      const first = missing[0].isGroup ? missing[0].el[0] : missing[0].el;
      bar.querySelector(".jh-sb-warn").style.cursor = "pointer";
      bar.querySelector(".jh-sb-warn").addEventListener("click", () => {
        try { first.scrollIntoView({ behavior: "smooth", block: "center" }); first.focus?.(); } catch {}
      });
    } else {
      go.addEventListener("click", () => {
        bar.remove();
        learnFromPage();               // capture final answers before navigation
        toast("Submitting…");
        try { submitBtn.click(); }
        catch { toast("Could not click submit — please click it yourself.", true); }
      });
    }
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
        job_id: armedJobId,
        fields: entries.map((e) => e.field),
        ai_fill: true,
      });
    } catch (e) {
      onStatus({ error: e.message });
      return;
    }
    const answers = data.answers || {};
    const aiKeys = new Set(data.ai_keys || []);
    let filled = 0, ai = 0, firstFilled = null;
    for (const entry of entries) {
      const v = answers[entry.key];
      // Custom dropdowns (Workday/react-select) need a real open→click gesture
      // and are async; everything else fills synchronously. One misbehaving
      // widget must never abort the rest of the form — swallow per-field.
      let ok = false;
      try {
        ok = entry.isCustomSelect
          ? (entry.msSearch ? await fillMultiSelectSearch(entry.el, v) : await fillCustomSelect(entry.el, v))
          : fillField(entry, v);
      } catch { ok = false; }
      if (ok) {
        filled++;
        if (!firstFilled) firstFilled = entry.isGroup ? entry.el[0] : (entry.isCustomSelect ? entry.el : entry.el);
        const isAi = aiKeys.has(entry.key);
        if (isAi) ai++;
        outline(entry, isAi);
      }
    }
    await closeAnyPopup();  // never leave a dropdown popup hanging after the run
    // Attach the resume PDF (tailored for this job when we have one) so the
    // file upload isn't the one step left to do by hand.
    const meta = pageMeta();
    const resumeInfo = await attachResume({ url: meta.url, title: meta.title, company: meta.company, job_id: armedJobId });
    const resumeState = resumeInfo.state;

    // Bring the filled form into view — on many ATS pages it sits far below
    // the job description, so the user wouldn't otherwise see it happened.
    if (firstFilled) {
      try { firstFilled.scrollIntoView({ behavior: "smooth", block: "center" }); } catch { /* ignore */ }
    }
    // Offer a confirm-gated submit. Never auto-clicks — the bar's "Submit
    // application" button is the only path, and it's blocked while required
    // fields are empty. A single-page form only; multi-step wizards (Workday)
    // are handled separately and skip this.
    const submitBtn = filled > 0 ? findSubmitButton() : null;
    if (submitBtn) {
      submitBar(entries, submitBtn,
        `Filled ${filled}/${entries.length}${ai ? ` · ${ai} by AI` : ""}. Review, then submit.`,
        resumeInfo);
    }
    onStatus({ done: true, total: entries.length, filled, ai, resume: data.resume_source,
               ai_status: data.ai_status, resume_state: resumeState,
               resume_name: resumeInfo.filename || "", resume_source: resumeInfo.source || "",
               has_submit: !!submitBtn });
  }
  window.__jhRunFill = runFill;

  // Human-readable tail for the fill toast (e.g. AI key missing → essay
  // questions stay blank). Empty string when nothing to add.
  function fillNote(s) {
    if (!s) return "";
    const bits = [];
    if (s.resume_state === "attached") {
      bits.push((s.resume_source === "base" ? "BASE resume: " : "tailored resume: ")
                + (s.resume_name || "attached"));
    }
    else if (s.resume_state === "manual") bits.push("attach the resume yourself (custom uploader)");
    else if (s.resume_state === "error") bits.push("resume attach failed — add/tailor a resume first");
    if (s.ai_status === "no_key") bits.push("add an AI key in Settings to auto-draft the open questions");
    else if (s.ai_status === "no_resume") bits.push("add your resume in Settings to auto-draft open questions");
    return bits.length ? " · " + bits.join(" · ") : "";
  }

  // ── Floating button ──────────────────────────────────────────────────────────
  // Known ATS hosts — the button belongs here. On any OTHER host the page must
  // show strong application evidence (see below), so random login/signup/
  // checkout forms across the web never grow a JH button.
  const _ATS_HOST_RE = new RegExp([
    "greenhouse\\.io", "lever\\.co", "ashbyhq\\.com", "myworkdayjobs\\.com",
    "workday", "icims\\.com", "smartrecruiters\\.com", "jobvite\\.com",
    "bamboohr\\.com", "taleo\\.net", "adp\\.com", "workablejobs|workable\\.com",
    "breezy\\.hr", "jazzhr|applytojob\\.com", "recruitee\\.com",
    "oraclecloud\\.com", "successfactors|sapsf", "paylocity\\.com",
    "paycomonline", "ultipro|ukg\\.", "dayforcehcm", "eightfold\\.ai",
    "phenom(people)?\\.com", "avature\\.net", "pinpointhq\\.com",
    "teamtailor\\.com", "personio", "rippling\\.com", "gem\\.com",
    "dover\\.com", "wellfound\\.com", "hirebridge", "clearcompany",
    "jobs\\.apple\\.com", "careers?\\.",
  ].join("|"), "i");

  function isAtsContext() {
    if (_ATS_HOST_RE.test(location.hostname)) return true;
    // Unknown host: URL path or title must say this is a job application.
    return /job|career|apply|application|position|vacanc|opening|requisition/i
      .test(location.pathname + " " + document.title);
  }

  function looksLikeApplication() {
    if (!isAtsContext()) return false;
    // Workday (and similar ATS) render whole steps as custom widgets with NO
    // native inputs — e.g. an "Application Questions" step that is nothing but
    // button-dropdowns. Counting only input/select/textarea missed those and
    // the button never appeared. Count custom dropdowns too, and treat a
    // Workday formField step as an application outright.
    const wdFields = document.querySelectorAll("[data-automation-id^='formField-']").length;
    if (wdFields >= 2) return true;

    const native = [...document.querySelectorAll("input, textarea, select")].filter((el) => {
      const t = (el.type || "").toLowerCase();
      if (el.tagName === "INPUT" && SKIP_TYPES.has(t)) return false;
      return isVisible(el) && !el.disabled;
    });
    const customDD = [...document.querySelectorAll(
      "button[aria-haspopup='listbox'], [role='combobox'], [class*='select__control'], [data-automation-id='multiSelectContainer']"
    )].filter((el) => isVisible(el) && !el.disabled);
    const fieldCount = native.length + customDD.length;
    if (fieldCount < 3) return false;

    const hasFile = !!document.querySelector("input[type=file]");
    const blob = native
      .map((e) => `${labelFor(e)} ${e.name || ""} ${e.getAttribute("aria-label") || ""}`.toLowerCase())
      .join(" | ");
    const hasResume = hasFile || /resume|cv\b|curriculum/.test(blob);
    const hasName = /first name|last name|full name|\bname\b|given name|surname/.test(blob);
    const hasEmail = /e-?mail/.test(blob);
    // Strong evidence only — the old "any 6 fields" catch-all put the button
    // on every long form on the internet.
    return hasResume || (hasName && hasEmail);
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
  let armedJobId = "";   // exact job id from the app's Fill & Apply hash (#jh=<id>)
  if (isTop) {
    // Accept #jh=<jobId> (new) or #jh=1 (legacy boolean arm). The job id lets
    // the backend pick THIS job's tailored resume instead of guessing by URL.
    const jhMatch = (location.hash || "").match(/(?:^|[#&])jh=([^&]+)/);
    if (jhMatch) {
      const val = decodeURIComponent(jhMatch[1]);
      if (val && val !== "1") armedJobId = val;
      try {
        const cleaned = location.href.replace(/([#&])jh=[^&]+(&|$)/, (_m, p, s) => (s === "&" ? p : "")).replace(/#$/, "");
        history.replaceState(null, "", cleaned);
      } catch { /* ignore */ }
      send("armTab", { jobId: armedJobId }).catch(() => {});
      armAutofill = true;
    }
    // Also consult the background: a prior navigation in this tab may have armed it.
    send("isArmed", {}).then((r) => {
      if (r?.armed) { armAutofill = true; if (r.jobId) armedJobId = r.jobId; maybeAutofill(); }
    }).catch(() => {});
  }

  // Multi-step wizards (Workday, iCIMS): the tab STAYS armed across steps —
  // each new step's field set differs from the last filled one, which re-arms
  // an auto-fill. Disarm happens only on a real final-submit click (below) or
  // the background TTL. The old one-shot disarm-after-page-1 is why steps 2/3
  // never filled and the attachments step lost the tailored-resume job id.
  let lastFilledSig = "";
  let fillRunning = false;

  function fieldSig() {
    try {
      return scanFields().map((e) => e.field.label).sort().join("|");
    } catch { return ""; }
  }

  async function maybeAutofill() {
    if (!isTop || !armAutofill || fillRunning) return;
    const here = looksLikeApplication();
    if (!here && !childHasForm) return; // no form yet — wait for render
    // A new wizard step shows a different field set — re-allow the fill.
    const sig = here ? fieldSig() : `child:${location.href}`;
    if (autofillDone && sig === lastFilledSig) return;
    autofillDone = true;
    fillRunning = true;
    toast("Auto-filling from Job Hunter…");
    const handle = (s) => {
      fillRunning = false;
      if (s && s.done && s.filled > 0) {
        lastFilledSig = sig;   // this step is done; the next step re-triggers
        toast(`Filled ${s.filled}/${s.total}${s.ai ? ` · ${s.ai} by AI` : ""}${fillNote(s)} — review before submitting`);
      } else {
        // Nothing filled (wrong/empty form, or a later form is the real one).
        autofillDone = false;
        if (s && s.error) toast(s.error, true);
      }
    };
    if (here) await runFill(handle);
    else handle(await send("relayFill", {}));
  }

  // Disarm only when the user clicks a FINAL submit ("Submit application",
  // "Submit", "Finish") — "Next"/"Continue"/"Save and Continue" keep the arm.
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest?.("button, input[type=submit], [role=button], a");
    if (!t) return;
    const txt = norm(t.textContent || t.value || t.getAttribute("aria-label") || "");
    if (SUBMIT_TEXT_RE.test(txt) && !SUBMIT_SKIP_RE.test(txt) && !/next|continue/i.test(txt)) {
      send("disarmTab", {}).catch(() => {});
    }
  }, true);

  // The button is ALWAYS hosted in the top frame (fixed to the real window,
  // so it never scrolls away). A form in a child iframe registers with the
  // background, which tells the top frame to show the button; the click is
  // relayed back to the form frame.
  function mountButton() {
    if (!isTop) return;
    if (document.getElementById("jh-fab")) return;
    const fab = document.createElement("button");
    fab.id = "jh-fab";
    fab.title = "Fill this application with Job Hunter — drag to move";
    fab.textContent = "JH";
    const busy = (on) => {
      fab.classList.toggle("jh-loading", on);
      fab.textContent = on ? "…" : "JH";
    };

    // ── Position: user-draggable, remembered across every site ─────────────
    const setPos = (left, top) => {
      const W = 46, m = 4;
      left = Math.min(Math.max(left, m), window.innerWidth - W - m);
      top = Math.min(Math.max(top, m), window.innerHeight - W - m);
      fab.style.setProperty("left", `${left}px`, "important");
      fab.style.setProperty("top", `${top}px`, "important");
      fab.style.setProperty("right", "auto", "important");
      fab.style.setProperty("bottom", "auto", "important");
      return { left, top };
    };
    const defaultPos = () => setPos(window.innerWidth - 66, window.innerHeight - 66);
    try {
      chrome.storage.local.get("jh_fab_pos", ({ jh_fab_pos }) => {
        if (jh_fab_pos && typeof jh_fab_pos.left === "number") setPos(jh_fab_pos.left, jh_fab_pos.top);
        else defaultPos();
      });
    } catch { defaultPos(); }

    let dragged = false;
    fab.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      dragged = false;
      const startX = e.clientX, startY = e.clientY;
      const r = fab.getBoundingClientRect();
      const offX = startX - r.left, offY = startY - r.top;
      const move = (ev) => {
        if (!dragged && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 6) return;
        dragged = true;
        setPos(ev.clientX - offX, ev.clientY - offY);
      };
      const up = (ev) => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", up, true);
        if (dragged) {
          const pos = setPos(ev.clientX - offX, ev.clientY - offY);
          try { chrome.storage.local.set({ jh_fab_pos: pos }); } catch { /* ignore */ }
        }
      };
      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", up, true);
    });

    fab.addEventListener("click", async () => {
      if (dragged) { dragged = false; return; }   // a drag is not a fill request
      busy(true);
      const handle = (s) => {
        if (!s || s.error) toast((s && s.error) || "No form fields found on this page.", true);
        else if (s.done) toast(`Filled ${s.filled}/${s.total}${s.ai ? ` · ${s.ai} by AI` : ""}${fillNote(s)} — review before submitting`);
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
