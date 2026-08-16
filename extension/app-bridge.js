// Auto-pair bridge — runs only on the Job Hunter web app. Reads the app's own
// auth token from its localStorage and hands it to the extension, so the user
// never types a password in the extension (works for Google/OAuth signups too).
// Logging out of the web app clears the token here → signs the extension out.
(function () {
  let last = null;
  function sync() {
    let token = "";
    let user = null;
    try {
      token = localStorage.getItem("jh_token") || "";
      const raw = localStorage.getItem("jh_user") || "";
      user = raw ? JSON.parse(raw) : null;
    } catch (_e) { /* ignore */ }
    if (token === last) return;   // only message on change
    last = token;
    try {
      chrome.runtime.sendMessage({ type: "syncAuth", payload: { token, user } }, () => void chrome.runtime.lastError);
    } catch (_e) { /* extension context gone */ }
  }
  sync();                                   // on load
  window.addEventListener("storage", sync); // login/logout in another tab
  setInterval(sync, 4000);                  // catch same-tab login/logout
})();
