const $ = (id) => document.getElementById(id);
const send = (type, payload) =>
  new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type, payload }, (res) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (res?.error) return reject(new Error(res.error));
      resolve(res?.data);
    });
  });

function show(view) {
  ["view-login", "view-main", "view-loading"].forEach((v) => ($(v).hidden = v !== view));
}

async function refresh() {
  show("view-loading");
  try {
    const { user } = await send("me");
    if (user) {
      $("user-email").textContent = user.email;
      $("logout").hidden = false;
      show("view-main");
    } else {
      $("logout").hidden = true;
      show("view-login");
    }
  } catch {
    show("view-login");
  }
}

// Auto-pair: after signing into the web app, the app-bridge content script
// hands the token to the extension. This just re-checks for it.
$("recheck").addEventListener("click", async () => {
  $("login-err").hidden = true;
  const btn = $("recheck");
  btn.disabled = true; btn.textContent = "Connecting…";
  await refresh();
  const { user } = await send("me").catch(() => ({ user: null }));
  if (!user) {
    $("login-err").textContent = "Not connected yet. Open Job Hunter, sign in, then try again.";
    $("login-err").hidden = false;
  }
  btn.disabled = false; btn.textContent = "I've signed in — connect";
});

$("logout").addEventListener("click", async () => { await send("logout"); await refresh(); });

$("fill").addEventListener("click", async () => {
  const st = $("status");
  const setStatus = (cls, html) => { st.hidden = false; st.className = `status ${cls}`; st.innerHTML = html; };
  $("fill").disabled = true;
  setStatus("run", "Scanning the page…");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const res = await chrome.tabs.sendMessage(tab.id, { type: "fillPage" });
    if (!res) throw new Error("Open a job application page, then try again.");
    if (res.error) setStatus("err", res.error);
    else if (res.done) {
      const aiBit = res.ai ? ` · <b>${res.ai}</b> drafted by AI` : "";
      setStatus("ok", `Filled <b>${res.filled}</b> of <b>${res.total}</b> fields${aiBit}.<br>Using your <b>${res.resume}</b> resume. Review every answer before submitting.`);
    } else if (res.scanning) setStatus("run", `Answering ${res.scanning} fields…`);
  } catch (e) {
    setStatus("err", (e.message || "Could not reach the page.") + " Reload the application page if it was open before installing.");
  } finally {
    $("fill").disabled = false;
  }
});

refresh();
