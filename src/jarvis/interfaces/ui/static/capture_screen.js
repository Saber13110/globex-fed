/* capture_screen.js — capture d'écran par zone (getDisplayMedia + crop) */
(function () {
  "use strict";

  let _armed = false;
  let _stream = null;
  let _video = null;

  function authHeaders() {
    return window.Jarvis && window.Jarvis.authHeaders ? window.Jarvis.authHeaders() : {};
  }

  function ensureOverlay() {
    let overlay = document.getElementById("capture-overlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "capture-overlay";
    overlay.className = "capture-overlay";
    overlay.hidden = true;
    overlay.innerHTML =
      '<div class="capture-overlay-hint">Glissez pour sélectionner la zone · Échap pour annuler</div>'
      + '<div id="capture-selection" class="capture-selection"></div>';
    document.body.appendChild(overlay);
    return overlay;
  }

  function ensureArmedBar() {
    let bar = document.getElementById("capture-armed-bar");
    if (bar) return bar;

    bar = document.createElement("div");
    bar.id = "capture-armed-bar";
    bar.className = "capture-armed-bar";
    bar.hidden = true;
    bar.innerHTML =
      '<span class="capture-armed-label">● Capture active</span>'
      + '<button type="button" id="capture-zone-btn" class="capture-zone-btn">Sélectionner une zone</button>'
      + '<button type="button" id="capture-armed-close" class="capture-armed-close" title="Désactiver">×</button>';
    document.body.appendChild(bar);

    bar.querySelector("#capture-zone-btn")?.addEventListener("click", () => {
      window.ScreenCapture.captureRegion().then((blob) => {
        if (blob) window.ScreenCapture.uploadAndNotify(blob);
      });
    });
    bar.querySelector("#capture-armed-close")?.addEventListener("click", () => {
      window.ScreenCapture.disarm();
      if (window._onScreenCaptureDisarm) window._onScreenCaptureDisarm();
    });
    return bar;
  }

  function updateArmedUI() {
    const bar = ensureArmedBar();
    bar.hidden = !_armed;
    document.getElementById("hc-screen")?.classList.toggle("active", _armed);
  }

  async function ensureVideo() {
    if (!_stream) throw new Error("Flux écran indisponible — réactivez la capture.");
    if (!_video) {
      _video = document.createElement("video");
      _video.muted = true;
      _video.playsInline = true;
      _video.srcObject = _stream;
    }
    if (_video.readyState < 2) {
      await _video.play();
      await new Promise((resolve) => {
        if (_video.videoWidth > 0) resolve();
        else _video.addEventListener("loadeddata", resolve, { once: true });
      });
    }
    return _video;
  }

  function waitForRegionSelection() {
    return new Promise((resolve) => {
      const overlay = ensureOverlay();
      const sel = overlay.querySelector("#capture-selection");
      overlay.hidden = false;
      sel.style.display = "none";
      sel.style.left = "0";
      sel.style.top = "0";
      sel.style.width = "0";
      sel.style.height = "0";

      let startX = 0;
      let startY = 0;
      let dragging = false;

      function cleanup(result) {
        overlay.hidden = true;
        window.removeEventListener("keydown", onKey);
        overlay.removeEventListener("mousedown", onDown);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        resolve(result);
      }

      function onKey(e) {
        if (e.key === "Escape") cleanup(null);
      }

      function onDown(e) {
        if (e.button !== 0) return;
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        sel.style.display = "block";
        sel.style.left = startX + "px";
        sel.style.top = startY + "px";
        sel.style.width = "0";
        sel.style.height = "0";
        e.preventDefault();
      }

      function onMove(e) {
        if (!dragging) return;
        const x = Math.min(startX, e.clientX);
        const y = Math.min(startY, e.clientY);
        const w = Math.abs(e.clientX - startX);
        const h = Math.abs(e.clientY - startY);
        sel.style.left = x + "px";
        sel.style.top = y + "px";
        sel.style.width = w + "px";
        sel.style.height = h + "px";
      }

      function onUp(e) {
        if (!dragging) return;
        dragging = false;
        const x = Math.min(startX, e.clientX);
        const y = Math.min(startY, e.clientY);
        const w = Math.abs(e.clientX - startX);
        const h = Math.abs(e.clientY - startY);
        if (w < 12 || h < 12) {
          cleanup(null);
          return;
        }
        cleanup({ x, y, w, h });
      }

      window.addEventListener("keydown", onKey);
      overlay.addEventListener("mousedown", onDown);
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  }

  async function cropRegion(rect) {
    const video = await ensureVideo();
    const scaleX = video.videoWidth / window.innerWidth;
    const scaleY = video.videoHeight / window.innerHeight;
    const sx = Math.round(rect.x * scaleX);
    const sy = Math.round(rect.y * scaleY);
    const sw = Math.round(rect.w * scaleX);
    const sh = Math.round(rect.h * scaleY);

    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, sw);
    canvas.height = Math.max(1, sh);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, sx, sy, sw, sh, 0, 0, sw, sh);

    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/png", 0.92);
    });
  }

  async function arm() {
    if (_armed && _stream) return true;
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error("Capture non supportée par ce navigateur.");
    }
    try {
      _stream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: "browser" },
        audio: false,
      });
      _stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        window.ScreenCapture.disarm();
        if (window._onScreenCaptureDisarm) window._onScreenCaptureDisarm();
      });
      _video = null;
      _armed = true;
      updateArmedUI();
      return true;
    } catch (err) {
      _armed = false;
      _stream = null;
      updateArmedUI();
      throw err;
    }
  }

  function disarm() {
    _armed = false;
    if (_stream) {
      _stream.getTracks().forEach((t) => t.stop());
      _stream = null;
    }
    _video = null;
    updateArmedUI();
  }

  async function captureRegion() {
    if (!_armed) await arm();
    const rect = await waitForRegionSelection();
    if (!rect) return null;
    return cropRegion(rect);
  }

  function buildDownloadUrl(spec) {
    if (!spec || !spec.capture_id) return "";
    const q = new URLSearchParams({
      capture_id: spec.capture_id,
      filename: spec.filename || "capture.png",
    });
    return "/api/globex/capture/download?" + q.toString();
  }

  async function uploadBlob(blob, hint) {
    const fd = new FormData();
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    fd.append("file", blob, "capture-" + ts + ".png");
    if (hint) fd.append("hint", String(hint).slice(0, 300));
    const resp = await fetch("/api/globex/capture", {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.detail || "Upload capture échoué");
    }
    return data.capture_download || data;
  }

  async function uploadAndNotify(blob, hint, msgWrap) {
    try {
      const spec = await uploadBlob(blob, hint);
      if (window.Jarvis?.notify) {
        window.Jarvis.notify({ kind: "success", text: "Capture enregistrée" });
      }
      if (msgWrap && window._appendGlobexCaptureLink) {
        window._appendGlobexCaptureLink(msgWrap, spec);
      }
      return spec;
    } catch (err) {
      if (window.Jarvis?.notify) {
        window.Jarvis.notify({ kind: "error", text: err.message || "Erreur capture" });
      }
      throw err;
    }
  }

  window.ScreenCapture = {
    isArmed: () => _armed,
    arm,
    disarm,
    captureRegion,
    uploadBlob,
    uploadAndNotify,
    buildDownloadUrl,
  };
})();
