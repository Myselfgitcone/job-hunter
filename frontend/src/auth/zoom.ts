// The auth page is drawn at a 1728×911 reference and scaled with CSS zoom on
// <body> so a 13" laptop and a 27" monitor both see it filling the screen.
// The app after login renders at native scale: call clearZoom() on login.

const REF_W = 1728, REF_H = 911, MIN = 0.62, MAX = 1.25;

function computeZoom(): number {
  if (window.innerWidth < 768) return 1;   // phones: native scale, the CSS breakpoints take over
  const z = Math.min(window.innerWidth / REF_W, window.innerHeight / REF_H);
  return Math.max(MIN, Math.min(MAX, z));
}

/** Scale <body> to the current viewport and publish the zoomed viewport size
 *  as --au-vh / --au-vw (100vh / 100vw do not account for CSS zoom). */
export function applyZoom() {
  const z = computeZoom();
  document.body.style.zoom = String(z);
  const r = document.documentElement.style;
  r.setProperty("--au-zoom", String(z));
  r.setProperty("--au-vh", `${window.innerHeight / z}px`);
  r.setProperty("--au-vw", `${window.innerWidth / z}px`);
}

export function clearZoom() {
  document.body.style.zoom = "";
  const r = document.documentElement.style;
  r.removeProperty("--au-zoom"); r.removeProperty("--au-vh"); r.removeProperty("--au-vw");
}
