(() => {
  const statusEl = document.getElementById("status");
  const btnFs = document.getElementById("btn-fs");
  const btnMirror = document.getElementById("btn-mirror");

  async function enterFullscreen() {
    const root = document.documentElement;
    try {
      if (!document.fullscreenElement) {
        await root.requestFullscreen();
      }
    } catch (e) {
      console.warn("fullscreen failed", e);
    }
  }

  // Mirror defaults ON in backend; label updates from /api/status
  window.addEventListener("load", () => {
    enterFullscreen();
  });

  // First tap/click anywhere → fullscreen (tablet-friendly)
  let fsArmed = true;
  document.addEventListener(
    "pointerdown",
    () => {
      if (fsArmed) {
        fsArmed = false;
        enterFullscreen();
      }
    },
    { passive: true }
  );

  btnFs.addEventListener("click", (e) => {
    e.stopPropagation();
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      enterFullscreen();
    }
  });

  btnMirror.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      const res = await fetch("/api/mirror", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      btnMirror.textContent = data.mirror ? "Mirror: ON" : "Mirror: OFF";
    } catch (err) {
      console.warn(err);
    }
  });

  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      statusEl.textContent = `${data.status} · ${data.fps} fps · poses ${data.poses}`;
      btnMirror.textContent = data.mirror ? "Mirror: ON" : "Mirror: OFF";
    } catch (e) {
      statusEl.textContent = "backend offline";
    }
  }

  setInterval(pollStatus, 1000);
  pollStatus();
})();
