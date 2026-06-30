/* accompaniment.js — Mode Accompagnement pour l'admin Globex (vanilla, autonome)
 *
 * Petit onglet transparent qui suit l'admin : partage d'écran continu +
 * suggestions contextuelles (vision Gemini côté backend Jarvis). L'onglet
 * RÉPOND lui-même (réponse inline) ; la sidebar Jarvis reste dispo pour le chat
 * complet. Aucune redirection vers une autre fenêtre.
 *
 * Conçu pour ne RIEN casser dans Angular : aucun composant/service modifié,
 * injecté via <script> dans index.html, styles préfixés « acc2- ».
 *
 * Backend = Jarvis (port 8013), surchargeable via window.JARVIS_ACC_BASE.
 * Les frames transitent en RAM (jamais stockées).
 */
(function () {
  "use strict";

  var ACC_BASE = window.JARVIS_ACC_BASE || "http://127.0.0.1:8013";

  var TICK_MS = 2500;
  var HEARTBEAT_MS = 60000;
  var IDLE_MS = 25000;
  var FRAME_MAX_W = 1100;
  var OPACITY_LEVELS = [1, 0.82, 0.62, 0.45];

  var _active = false;
  var _stream = null;
  var _video = null;
  var _sessionId = null;
  var _timer = null;
  var _inflight = false;
  var _lastFrameHash = "";
  var _lastTickAt = 0;
  var _cooldownUntil = 0;
  var _lastOverlayFp = "";
  var _dismissed = [];
  var _queue = [];
  var _lastActivity = Date.now();
  var _idleFired = false;
  var _stylesInjected = false;
  var _opIdx = 0;
  var _history = [];
  // Cible d'une suggestion cliquée : "here" (réponse inline), "sidebar"
  // (chat Jarvis de l'admin), "window" (fenêtre Jarvis :8013).
  var _target = "sidebar";

  function isLoggedIn() {
    try {
      return !!localStorage.getItem("globex_jwt");
    } catch (_) {
      return false;
    }
  }

  /* ───────── Styles isolés ───────── */
  function injectStyles() {
    if (_stylesInjected) return;
    _stylesInjected = true;
    var css =
      ".acc2-launch{position:fixed;right:22px;bottom:22px;z-index:99400;display:flex;align-items:center;gap:8px;" +
      "padding:10px 14px;border-radius:99px;border:1px solid rgba(120,170,255,.4);background:rgba(12,15,28,.82);" +
      "color:#e8f0ff;font:600 12.5px/1 'Inter',system-ui,sans-serif;cursor:pointer;backdrop-filter:blur(22px);" +
      "box-shadow:0 14px 40px rgba(0,0,0,.5)}" +
      ".acc2-launch:hover{border-color:rgba(150,190,255,.7);background:rgba(20,26,46,.9)}" +
      ".acc2-launch .acc2-d{width:8px;height:8px;border-radius:50%;background:#4a9eff;box-shadow:0 0 8px #4a9eff}" +
      ".acc2-panel{position:fixed;right:22px;bottom:22px;z-index:99400;width:330px;max-width:calc(100vw - 44px);" +
      "color:rgba(232,240,255,.94);background:rgba(8,13,32,.66);border:1px solid rgba(120,170,255,.18);" +
      "border-radius:16px;backdrop-filter:blur(28px) saturate(180%);box-shadow:0 18px 48px rgba(0,0,0,.55);" +
      "font-family:'Inter',system-ui,sans-serif;overflow:hidden;transition:opacity .15s ease}" +
      ".acc2-head{display:flex;align-items:center;gap:6px;padding:10px 12px;cursor:move;user-select:none}" +
      ".acc2-dot{width:8px;height:8px;border-radius:50%;background:#36d399;box-shadow:0 0 8px #36d399;flex:0 0 auto;" +
      "animation:acc2pulse 2.4s ease-in-out infinite}" +
      "@keyframes acc2pulse{0%,100%{opacity:1}50%{opacity:.35}}" +
      ".acc2-title{flex:1 1 auto;font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
      ".acc2-ico{flex:0 0 auto;width:24px;height:24px;border:none;background:transparent;color:rgba(220,232,255,.6);" +
      "font-size:14px;line-height:1;cursor:pointer;border-radius:6px;display:flex;align-items:center;justify-content:center}" +
      ".acc2-ico:hover{color:#fff;background:rgba(220,232,255,.12)}" +
      ".acc2-body{padding:0 12px 12px}" +
      ".acc2-text{margin:0 0 10px;font-size:12.5px;line-height:1.5;color:rgba(220,232,255,.82)}" +
      ".acc2-actions{display:flex;flex-wrap:wrap;gap:6px}" +
      ".acc2-btn{border:1px solid rgba(120,170,255,.4);background:rgba(80,130,255,.18);color:#eaf2ff;font:500 12px/1.25 'Inter';" +
      "padding:7px 10px;border-radius:9px;cursor:pointer;text-align:left}" +
      ".acc2-btn:hover{background:rgba(80,130,255,.34);border-color:rgba(150,190,255,.7)}" +
      ".acc2-btn.ghost{border-color:rgba(220,232,255,.18);background:transparent;color:rgba(220,232,255,.55)}" +
      ".acc2-quick{margin:0 0 10px}" +
      ".acc2-cap-btn{width:100%;border:1px solid rgba(54,211,153,.45);background:rgba(54,211,153,.14);color:#e8fff5;" +
      "font:600 12px/1.3 'Inter';padding:9px 10px;border-radius:10px;cursor:pointer;text-align:left}" +
      ".acc2-cap-btn:hover{background:rgba(54,211,153,.28);border-color:rgba(54,211,153,.7)}" +
      ".acc2-cap-btn:disabled{opacity:.55;cursor:wait}" +
      ".acc2-reply{margin-top:10px;padding:10px 12px;border-radius:10px;background:rgba(54,211,153,.08);" +
      "border:1px solid rgba(54,211,153,.22);font-size:12.5px;line-height:1.55;color:#e8f0ff;white-space:pre-wrap;" +
      "max-height:240px;overflow:auto;display:none}" +
      ".acc2-reply.show{display:block}" +
      ".acc2-targets{display:flex;gap:4px;margin:0 0 9px;padding:3px;border-radius:9px;background:rgba(120,150,220,.1)}" +
      ".acc2-seg{flex:1 1 0;border:none;background:transparent;color:rgba(220,232,255,.6);font:600 11px/1.2 'Inter';" +
      "padding:6px 4px;border-radius:7px;cursor:pointer;white-space:nowrap}" +
      ".acc2-seg:hover{color:#eaf2ff}" +
      ".acc2-seg.on{background:rgba(80,130,255,.45);color:#fff}" +
      ".acc2-min-state .acc2-body{display:none}.acc2-min-state{width:230px}";
    var st = document.createElement("style");
    st.id = "acc2-styles";
    st.textContent = css;
    document.head.appendChild(st);
  }

  /* ───────── Lanceur ───────── */
  function ensureLauncher() {
    injectStyles();
    var btn = document.getElementById("acc2-launch");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "acc2-launch";
      btn.type = "button";
      btn.className = "acc2-launch";
      btn.innerHTML = '<span class="acc2-d"></span><span>Activer l\u2019accompagnement</span>';
      btn.addEventListener("click", function () {
        start().catch(function (err) {
          alert((err && err.message) || "Partage d\u2019\u00e9cran refus\u00e9.");
        });
      });
      document.body.appendChild(btn);
    }
    // Visible dès qu'on est connecté (n'importe quelle page de l'app), masqué si actif.
    btn.style.display = isLoggedIn() && !_active ? "" : "none";
  }

  /* ───────── Panneau ───────── */
  function ensureQuickCaptureRow(panel) {
    if (panel.querySelector("#acc2-quick")) return;
    var targets = panel.querySelector("#acc2-targets");
    var textEl = panel.querySelector("#acc2-text");
    if (!targets || !textEl) return;
    var quick = document.createElement("div");
    quick.className = "acc2-quick";
    quick.id = "acc2-quick";
    quick.innerHTML =
      '<button type="button" class="acc2-cap-btn" id="acc2-cap-quick">\uD83D\uDCF7 Coller la capture dans la sidebar Jarvis</button>';
    targets.parentNode.insertBefore(quick, textEl);
  }

  function wirePanelControls(panel) {
    var capHead = panel.querySelector("#acc2-cap");
    if (capHead && !capHead._accWired) {
      capHead._accWired = true;
      capHead.addEventListener("click", captureToSidebar);
    }
    var capQuick = panel.querySelector("#acc2-cap-quick");
    if (capQuick && !capQuick._accWired) {
      capQuick._accWired = true;
      capQuick.addEventListener("click", captureToSidebar);
    }
    var segs = panel.querySelectorAll(".acc2-seg");
    Array.prototype.forEach.call(segs, function (seg) {
      if (seg._accWired) return;
      seg._accWired = true;
      if (seg.getAttribute("data-t") === _target) seg.classList.add("on");
      seg.addEventListener("click", function () {
        _target = seg.getAttribute("data-t") || "sidebar";
        Array.prototype.forEach.call(segs, function (s) {
          s.classList.toggle("on", s === seg);
        });
      });
    });
  }

  function ensurePanel() {
    injectStyles();
    var panel = document.getElementById("acc2-panel");
    if (panel) {
      ensureQuickCaptureRow(panel);
      wirePanelControls(panel);
      return panel;
    }
    panel = document.createElement("div");
    panel.id = "acc2-panel";
    panel.className = "acc2-panel";
    panel.style.opacity = OPACITY_LEVELS[_opIdx];
    panel.innerHTML =
      '<div class="acc2-head" id="acc2-head">' +
      '<span class="acc2-dot"></span>' +
      '<span class="acc2-title" id="acc2-title">Jarvis t\u2019accompagne</span>' +
      '<button type="button" class="acc2-ico" id="acc2-cap" title="Capturer l\u2019\u00e9cran et l\u2019envoyer \u00e0 la sidebar Jarvis">\uD83D\uDCF7</button>' +
      '<button type="button" class="acc2-ico" id="acc2-opacity" title="Transparence">\u25d0</button>' +
      '<button type="button" class="acc2-ico" id="acc2-min" title="R\u00e9duire">\u2013</button>' +
      '<button type="button" class="acc2-ico" id="acc2-x" title="Arr\u00eater">\u00d7</button>' +
      "</div>" +
      '<div class="acc2-body">' +
      '<div class="acc2-targets" id="acc2-targets">' +
      '<button type="button" class="acc2-seg" data-t="here" title="R\u00e9pondre dans cet onglet">\uD83D\uDCAC Ici</button>' +
      '<button type="button" class="acc2-seg" data-t="sidebar" title="Envoyer au chat Jarvis de la barre lat\u00e9rale">\u2B05 Sidebar</button>' +
      '<button type="button" class="acc2-seg" data-t="window" title="Ouvrir dans la fen\u00eatre Jarvis">\u2922 Fen\u00eatre</button>' +
      "</div>" +
      '<div class="acc2-quick" id="acc2-quick">' +
      '<button type="button" class="acc2-cap-btn" id="acc2-cap-quick">\uD83D\uDCF7 Coller la capture dans la sidebar Jarvis</button>' +
      "</div>" +
      '<p class="acc2-text" id="acc2-text">Je surveille ton \u00e9cran. Voici ce que tu peux me demander.</p>' +
      '<div class="acc2-actions" id="acc2-actions"></div>' +
      '<div class="acc2-reply" id="acc2-reply"></div>' +
      "</div>";
    document.body.appendChild(panel);
    panel.querySelector("#acc2-x").addEventListener("click", stop);
    panel.querySelector("#acc2-min").addEventListener("click", function () {
      panel.classList.toggle("acc2-min-state");
    });
    panel.querySelector("#acc2-opacity").addEventListener("click", function () {
      _opIdx = (_opIdx + 1) % OPACITY_LEVELS.length;
      panel.style.opacity = OPACITY_LEVELS[_opIdx];
    });
    makeDraggable(panel, panel.querySelector("#acc2-head"));
    wirePanelControls(panel);
    return panel;
  }

  /* ───────── Déplacement ───────── */
  function makeDraggable(panel, handle) {
    var sx = 0, sy = 0, ox = 0, oy = 0, dragging = false;
    handle.addEventListener("mousedown", function (e) {
      if (e.target.closest("button")) return; // ne pas drag quand on clique une icône
      dragging = true;
      sx = e.clientX;
      sy = e.clientY;
      var r = panel.getBoundingClientRect();
      ox = r.left;
      oy = r.top;
      panel.style.right = "auto";
      panel.style.bottom = "auto";
      panel.style.left = ox + "px";
      panel.style.top = oy + "px";
      e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      var nx = ox + (e.clientX - sx);
      var ny = oy + (e.clientY - sy);
      nx = Math.max(4, Math.min(nx, window.innerWidth - 80));
      ny = Math.max(4, Math.min(ny, window.innerHeight - 40));
      panel.style.left = nx + "px";
      panel.style.top = ny + "px";
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
    });
  }

  function renderOverlay(ov) {
    var panel = ensurePanel();
    var titleEl = panel.querySelector("#acc2-title");
    var textEl = panel.querySelector("#acc2-text");
    var actionsEl = panel.querySelector("#acc2-actions");
    if (titleEl) titleEl.textContent = ov.title || "Jarvis t\u2019accompagne";
    if (textEl) textEl.textContent = ov.body || "";
    if (actionsEl) {
      actionsEl.innerHTML = "";
      (ov.actions || []).forEach(function (a) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "acc2-btn" + (a.type === "dismiss" ? " ghost" : "");
        btn.textContent = a.label || "Action";
        btn.addEventListener("click", function () {
          runAction(a, btn);
        });
        actionsEl.appendChild(btn);
      });
    }
    panel.classList.remove("acc2-min-state");
  }

  function showReply(text) {
    var panel = ensurePanel();
    var rep = panel.querySelector("#acc2-reply");
    if (!rep) return;
    rep.textContent = text;
    rep.classList.add("show");
    panel.classList.remove("acc2-min-state");
  }

  function runAction(a, btn) {
    if (!a) return;
    if (a.type === "dismiss") {
      if (a.fingerprint) _dismissed.push(a.fingerprint);
      ensurePanel().classList.add("acc2-min-state");
      return;
    }
    if (a.type !== "chat_prompt" || !a.text) return;
    // Route selon la cible choisie par l'utilisateur (segmented control).
    if (_target === "sidebar") {
      sendToSidebar(a.text, btn);
    } else if (_target === "window") {
      sendToWindow(a.text, btn);
    } else {
      askInline(a.text, btn);
    }
  }

  function flashBtn(btn, label) {
    if (!btn) return;
    var prev = btn.textContent;
    btn.textContent = label;
    setTimeout(function () {
      btn.textContent = prev;
    }, 1400);
  }

  // Ouvre la sidebar Jarvis et y injecte texte + capture (optionnelle).
  function pushPromptToSidebar(text, frame, autosend) {
    var detail = {
      text: text || "",
      autosend: autosend === true,
    };
    if (frame && frame.base64) {
      detail.imageBase64 = frame.base64;
      detail.mime = frame.mime || "image/jpeg";
      detail.name = "capture-ecran.jpg";
    }
    window.dispatchEvent(new CustomEvent("jarvis:prompt", { detail: detail }));
  }

  // Écrit la suggestion dans le chat Jarvis de la barre latérale admin et l'envoie.
  function sendToSidebar(text, btn) {
    grabFrame()
      .then(function (frame) {
        pushPromptToSidebar(text, frame, true);
        flashBtn(btn, frame ? "\u27a4 Sidebar + \uD83D\uDCF7" : "\u27a4 Sidebar");
      })
      .catch(function () {
        pushPromptToSidebar(text, null, true);
        flashBtn(btn, "\u27a4 Sidebar");
      });
  }

  // Ouvre la fenêtre Jarvis (:8013) en y pré-remplissant la suggestion.
  function sendToWindow(text, btn) {
    window.dispatchEvent(
      new CustomEvent("jarvis:window", { detail: { text: text } })
    );
    flashBtn(btn, "\u2922 Fen\u00eatre");
  }

  // Capture l'écran courant et la colle (pièce jointe) dans le chat Jarvis sidebar.
  function captureToSidebar() {
    var panel = ensurePanel();
    var quickBtn = panel.querySelector("#acc2-cap-quick");
    var headBtn = panel.querySelector("#acc2-cap");
    if (quickBtn) quickBtn.disabled = true;
    if (headBtn) headBtn.disabled = true;
    showReply("Capture de l\u2019\u00e9cran\u2026");
    grabFrame()
      .then(function (frame) {
        if (!frame) {
          showReply(
            "Impossible de capturer l\u2019\u00e9cran. V\u00e9rifie que le partage d\u2019\u00e9cran est actif."
          );
          return;
        }
        pushPromptToSidebar(
          "Voici une capture de mon \u00e9cran. Que peux-tu m\u2019aider \u00e0 faire ?",
          frame,
          false
        );
        showReply(
          "\uD83D\uDCF7 Capture coll\u00e9e dans la sidebar Jarvis (aper\u00e7u \uD83D\uDCCE). V\u00e9rifie le chat \u00e0 droite, puis envoie."
        );
      })
      .catch(function () {
        showReply("\u00c9chec de la capture d\u2019\u00e9cran.");
      })
      .then(function () {
        if (quickBtn) quickBtn.disabled = false;
        if (headBtn) headBtn.disabled = false;
      });
  }

  // L'accompagnement répond lui-même EN REGARDANT l'écran (anti-hallucination).
  // On capture la frame courante et on l'envoie à /accompaniment/ask : la
  // réponse est ainsi ancrée sur la page réellement affichée.
  function askInline(text, btn) {
    var prev = btn ? btn.textContent : "";
    if (btn) {
      btn.textContent = "\u2026";
      btn.disabled = true;
    }
    showReply("Jarvis regarde ton \u00e9cran\u2026");
    var restore = function () {
      if (btn) {
        btn.textContent = prev;
        btn.disabled = false;
      }
    };
    grabFrame()
      .then(function (frame) {
        var body = {
          session_id: _sessionId,
          question: text,
          ui_context: collectContext(),
          ui_language: "fr",
        };
        if (frame) {
          body.frame_base64 = frame.base64;
          body.frame_mime_type = frame.mime;
        }
        return fetch(ACC_BASE + "/api/globex/accompaniment/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      })
      .then(function (r) {
        return r && r.ok ? r.json() : null;
      })
      .then(function (d) {
        var reply = (d && d.reply) || "(pas de r\u00e9ponse)";
        showReply(reply);
        _history.push({ role: "user", content: text });
        _history.push({ role: "assistant", content: reply });
        restore();
      })
      .catch(function () {
        showReply("Connexion \u00e0 Jarvis impossible. V\u00e9rifie que Jarvis tourne (port 8013).");
        restore();
      });
  }

  /* ───────── Frame ───────── */
  function ensureVideo() {
    return new Promise(function (resolve) {
      if (!_stream) return resolve(null);
      if (_video && _video.readyState >= 2 && _video.videoWidth > 0) return resolve(_video);
      if (!_video) {
        _video = document.createElement("video");
        _video.muted = true;
        _video.playsInline = true;
        _video.srcObject = _stream;
      }
      _video.play().catch(function () {});
      if (_video.videoWidth > 0) return resolve(_video);
      var done = false;
      _video.addEventListener(
        "loadeddata",
        function () {
          if (!done) {
            done = true;
            resolve(_video.videoWidth > 0 ? _video : null);
          }
        },
        { once: true }
      );
      setTimeout(function () {
        if (!done) {
          done = true;
          resolve(_video.videoWidth > 0 ? _video : null);
        }
      }, 1500);
    });
  }

  function quickHash(str) {
    var h = 5381;
    var step = Math.max(1, Math.floor(str.length / 4096));
    for (var i = 0; i < str.length; i += step) {
      h = (h * 33 + str.charCodeAt(i)) >>> 0;
    }
    return String(str.length) + ":" + h.toString(36);
  }

  function grabFrame() {
    return ensureVideo().then(function (video) {
      if (!video) return null;
      var scale = Math.min(1, FRAME_MAX_W / video.videoWidth);
      var w = Math.max(1, Math.round(video.videoWidth * scale));
      var h = Math.max(1, Math.round(video.videoHeight * scale));
      var canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      canvas.getContext("2d").drawImage(video, 0, 0, w, h);
      var dataUrl;
      try {
        dataUrl = canvas.toDataURL("image/jpeg", 0.6);
      } catch (_) {
        return null;
      }
      var base64 = (dataUrl.split(",")[1]) || "";
      if (!base64) return null;
      return { base64: base64, mime: "image/jpeg", hash: quickHash(base64) };
    });
  }

  /* ───────── Événements ───────── */
  function pushEvent(type, priority, needsVision) {
    _queue.push({ type: type, priority: priority, needsVision: !!needsVision });
  }

  function dequeue() {
    if (!_queue.length) return null;
    _queue.sort(function (a, b) {
      return a.priority - b.priority;
    });
    var ev = _queue.shift();
    _queue = [];
    return ev;
  }

  function collectContext() {
    var pageId = "admin";
    try {
      var seg = location.pathname.replace(/^\//, "").split("/");
      if (seg[0] === "admin" && seg[1]) pageId = seg[1];
      else if (seg[0]) pageId = seg[0];
    } catch (_) {}
    return { page_id: pageId, route: location.pathname + location.hash, title: document.title };
  }

  /* ───────── Planificateur ───────── */
  function tickOnce() {
    if (!_active || _inflight) return;
    var now = Date.now();
    if (now < _cooldownUntil) return;

    if (!_queue.length && now - _lastActivity > IDLE_MS && !_idleFired) {
      _idleFired = true;
      pushEvent("idle", 1, true);
    }

    var ev = dequeue();
    if (!ev) {
      if (now - _lastTickAt < HEARTBEAT_MS) return;
      ev = { type: "heartbeat", priority: 2, needsVision: true };
    }

    var needFrame = ev.needsVision || ev.priority <= 1;
    var framePromise = needFrame ? grabFrame() : Promise.resolve(null);

    framePromise.then(function (f) {
      var frame = null;
      if (f) {
        if (f.hash === _lastFrameHash && ev.priority >= 2) {
          _lastTickAt = now;
          return;
        }
        frame = f;
        _lastFrameHash = f.hash;
      }
      var body = {
        session_id: _sessionId,
        event: { type: ev.type, priority: ev.priority, payload: {} },
        ui_context: collectContext(),
        dismissed: _dismissed.slice(-20),
        ui_language: "fr",
      };
      if (frame) {
        body.frame_base64 = frame.base64;
        body.frame_mime_type = frame.mime;
      }
      _inflight = true;
      fetch(ACC_BASE + "/api/globex/accompaniment/tick", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (resp) {
          _lastTickAt = Date.now();
          return resp.ok ? resp.json() : null;
        })
        .then(function (data) {
          if (data) applyTick(data);
        })
        .catch(function () {})
        .then(function () {
          _inflight = false;
        });
    });
  }

  function applyTick(data) {
    var ov = data && data.overlay;
    if (!ov || !ov.show) return;
    if (ov.fingerprint && _dismissed.indexOf(ov.fingerprint) !== -1) return;
    if (ov.fingerprint && ov.fingerprint === _lastOverlayFp && ov.priority >= 2) return;
    _lastOverlayFp = ov.fingerprint || "";
    if (ov.cooldown_seconds) _cooldownUntil = Date.now() + ov.cooldown_seconds * 1000;
    renderOverlay(ov);
  }

  /* ───────── Activité ───────── */
  function onActivity() {
    _lastActivity = Date.now();
    _idleFired = false;
  }
  function onClick() {
    onActivity();
    pushEvent("click", 2, true);
  }
  function bindListeners() {
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onActivity, true);
    document.addEventListener("mousemove", onActivity, true);
  }
  function unbindListeners() {
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("keydown", onActivity, true);
    document.removeEventListener("mousemove", onActivity, true);
  }

  /* ───────── Cycle de vie ───────── */
  function start() {
    if (_active) return Promise.resolve(true);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      return Promise.reject(new Error("Partage d\u2019\u00e9cran non support\u00e9 par ce navigateur."));
    }
    return navigator.mediaDevices
      .getDisplayMedia({ video: { frameRate: { ideal: 1, max: 5 } }, audio: false })
      .then(function (stream) {
        _stream = stream;
        var track = stream.getVideoTracks()[0];
        if (track) track.addEventListener("ended", stop);
        _video = null;
        return fetch(ACC_BASE + "/api/globex/accompaniment/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ui_language: "fr" }),
        })
          .then(function (r) {
            return r.ok ? r.json() : {};
          })
          .catch(function () {
            return {};
          });
      })
      .then(function (d) {
        _sessionId = (d && d.session_id) || "local-" + Date.now();
        _active = true;
        _lastFrameHash = "";
        _lastOverlayFp = "";
        _cooldownUntil = 0;
        _lastActivity = Date.now();
        _idleFired = false;
        ensureLauncher();
        ensurePanel();
        bindListeners();
        _timer = setInterval(tickOnce, TICK_MS);
        pushEvent("navigation", 1, true);
        return true;
      });
  }

  function stop() {
    _active = false;
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    unbindListeners();
    if (_stream) {
      _stream.getTracks().forEach(function (t) {
        t.stop();
      });
      _stream = null;
    }
    _video = null;
    _queue = [];
    var sid = _sessionId;
    _sessionId = null;
    var panel = document.getElementById("acc2-panel");
    if (panel) panel.remove();
    ensureLauncher();
    if (sid) {
      fetch(ACC_BASE + "/api/globex/accompaniment/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid }),
      }).catch(function () {});
    }
  }

  // Le lanceur reste visible tant qu'on est connecté (routing Angular = pushState).
  setInterval(function () {
    if (!_active) ensureLauncher();
  }, 1500);
  window.addEventListener("popstate", function () {
    if (!_active) ensureLauncher();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureLauncher);
  } else {
    ensureLauncher();
  }

  window.JarvisAccompaniment = {
    start: start,
    stop: stop,
    isActive: function () {
      return _active;
    },
  };
})();
