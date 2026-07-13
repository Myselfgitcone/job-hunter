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

$("login").addEventListener("click", async () => {
  const email = $("email").value.trim();
  const password = $("password").value;
  $("login-err").hidden = true;
  if (!email || !password) { $("login-err").textContent = "Enter your email and password."; $("login-err").hidden = false; return; }
  $("login").disabled = true;
  $("login").textContent = "Signing in…";
  try {
    await send("login", { email, password });
    await refresh();
  } catch (e) {
    $("login-err").textContent = e.message || "Sign in failed.";
    $("login-err").hidden = false;
  } finally {
    $("login").disabled = false;
    $("login").textContent = "Sign in";
  }
});

$("password").addEventListener("keydown", (e) => { if (e.key === "Enter") $("login").click(); });

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
