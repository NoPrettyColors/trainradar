// Apply a saved theme choice, and touch density on touch screens, before first paint.
// A file rather than an inline script so the Content-Security-Policy can forbid inline scripts.
try { const t = localStorage.getItem("trainradar-theme"); if (t) document.documentElement.dataset.theme = t; } catch {}
if (matchMedia("(pointer: coarse)").matches) document.documentElement.dataset.density = "touch";
