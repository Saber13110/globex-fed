/* home.js — page Home runtime (chat-attach v5) */
(function () {
  "use strict";

  if (location.port === "8010") {
    const target =
      location.protocol + "//" + location.hostname + ":8011" + location.pathname + location.search + location.hash;
    location.replace(target);
    return;
  }

  const J = window.fedexV0;

  // ── Atmosphere + Mission Control ──────────────────────────────────
  J.mountAtmosphere();
  J.mountRooms({ mode: "home", pages: [], activePage: null, onNav: () => {} });

  // ── Stubs pour voice.js (tourne aussi dans cette page) ───────────
  // voice.js cherche addMsg / checkForMindmap en global
  window.addMsg = function (role, text = "", streaming = false) {
    if (streaming) {
      // Retourne une div temporaire que le VoiceClient remplit de chunks
      const div = document.createElement("div");
      div.className = "hcw-msg";
      div.dataset.streaming = "1";
      const roleEl = document.createElement("span");
      roleEl.className = "hcw-msg-role " + (role === "fedex_v0" ? "assistant" : "");
      roleEl.textContent = role === "fedex_v0" ? "FEDEX_V0" : "VOUS";
      const textEl = document.createElement("span");
      textEl.className = "hcw-msg-text";
      div.appendChild(roleEl);
      div.appendChild(textEl);
      // Si le widget chat est ouvert, on append
      const msgsEl = document.getElementById("hcw-chat-msgs");
      if (msgsEl && _ctrlState.chat) {
        msgsEl.appendChild(div);
        msgsEl.scrollTop = msgsEl.scrollHeight;
      }
      return textEl; // voice.js écrit dans .textContent de ce noeud
    }
    // Non-streaming : on recharge le widget si ouvert
    if (_ctrlState.chat) setTimeout(loadChatWidget, 800);
    return null;
  };
  window.checkForMindmap = function () {};

  // ── WebSocket session ID / send (pour mediapipe_vision.js) ───────
  let _ws = null;
  window._fedex_v0SessionId = () => null;
  window._fedex_v0WsSend = (data) => {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify(data));
    }
  };

  // ── Clock + date ──────────────────────────────────────────────────
  const JOURS = ["DIMANCHE","LUNDI","MARDI","MERCREDI","JEUDI","VENDREDI","SAMEDI"];
  const MOIS  = ["JANVIER","FÉVRIER","MARS","AVRIL","MAI","JUIN","JUILLET","AOÛT","SEPTEMBRE","OCTOBRE","NOVEMBRE","DÉCEMBRE"];

  function updateClock() {
    const t   = new Date();
    const pad = n => String(n).padStart(2, "0");
    const cl  = document.getElementById("home-clock");
    const dt  = document.getElementById("home-date");
    if (cl) cl.textContent = pad(t.getHours()) + ":" + pad(t.getMinutes());
    if (dt) dt.textContent = JOURS[t.getDay()] + ", " + t.getDate() + " " + MOIS[t.getMonth()] + " " + t.getFullYear();
  }
  updateClock();
  setInterval(updateClock, 1000);

  // ── État orbe ─────────────────────────────────────────────────────
  const STATE_DOTS = {
    idle:      { cls: "blue",   label: "AU REPOS" },
    listening: { cls: "blue",   label: "EN ÉCOUTE" },
    thinking:  { cls: "purple", label: "RÉFLEXION" },
    speaking:  { cls: "purple", label: "PARLE" },
    success:   { cls: "green",  label: "SUCCÈS" },
    offline:   { cls: "gray",   label: "HORS LIGNE" },
  };

  let _orb = null;
  let _currentState = "idle";

  function setOrbState(state) {
    _currentState = state;
    const meta = STATE_DOTS[state] || STATE_DOTS.idle;
    const dot = document.getElementById("status-dot");
    const lbl = document.getElementById("status-label");
    if (dot) dot.className = "status-dot " + meta.cls;
    if (lbl) lbl.textContent = meta.label;
    if (_orb) _orb.setState(state);
  }

  function initOrb() {
    if (typeof THREE === "undefined" || typeof FedexV0Orb === "undefined") {
      setTimeout(initOrb, 100);
      return;
    }
    // Cold boot wake : la séquence va mounter l'orbe sur #orb-canvas en
    // frozen, puis nous le rendra via injectWakeOrb() à l'entrée ONLINE.
    if (window.__fedex_v0WakeActive) return;
    const canvas = document.getElementById("orb-canvas");
    if (!canvas) return;
    _orb = new FedexV0Orb(canvas);
    setOrbState("idle");
  }
  initOrb();

  // ── Bascule depuis la séquence de réveil ────────────────────────────
  // wake_sequence.js appelle ça à l'entrée ONLINE : l'orbe partagé est
  // remis à home.js, qui prend la main pour les states voice/audio/music.
  window.__fedex_v0InjectOrb = function (orb) {
    _orb = orb;
    setOrbState("idle");
  };

  // ── body.view-active : source de vérité unique pour toutes les vues ─
  const _origViewActivate   = J.views.activate.bind(J.views);
  const _origViewDeactivate = J.views.deactivate.bind(J.views);
  J.views.activate = function (id, params) {
    _origViewActivate(id, params);
    document.body.classList.add("view-active");
  };
  J.views.deactivate = function (id) {
    _origViewDeactivate(id);
    // Différé : si activate() enchaîne, _active est déjà re-setté quand le check tourne
    Promise.resolve().then(() => {
      if (!J.views._active) document.body.classList.remove("view-active");
    });
  };

  // ── Sync état orbe depuis les events voice.js ─────────────────────
  const VOICE_ORB_MAP = {
    vad_start:   "listening",
    stt_done:    "thinking",
    llm_start:   "thinking",
    tts_start:   "speaking",
    tts_done:    "idle",
    interrupted: "listening",
  };
  window.addEventListener("fedex_v0:ws", (e) => {
    const msg = e.detail;
    if (VOICE_ORB_MAP[msg.type]) setOrbState(VOICE_ORB_MAP[msg.type]);
    if (msg.type === "tts_done" || msg.type === "done") {
      setTimeout(() => setOrbState("idle"), 1200);
    }
  });

  // ── Controls (pictos haut-gauche) ─────────────────────────────────
  const CTRL_DEFS = [
    { key: "mic",    id: "hc-mic" },
    { key: "screen", id: "hc-screen" },
    { key: "cam",    id: "hc-cam" },
    { key: "files",  id: "hc-files" },
    { key: "music",  id: "hc-music",  widget: "hc-widget-music" },
    { key: "chat",   id: "hc-chat",   widget: "hc-widget-chat" },
  ];

  const _ctrlState = {};
  CTRL_DEFS.forEach(c => { _ctrlState[c.key] = false; });

  function setCtrl(key, val) {
    _ctrlState[key] = val;
    const def = CTRL_DEFS.find(c => c.key === key);
    if (!def) return;
    const btn = document.getElementById(def.id);
    if (btn) btn.classList.toggle("active", val);
    if (def.widget) {
      const w = document.getElementById(def.widget);
      if (w) w.classList.toggle("is-open", val);
    }
  }

  async function toggleCtrl(key) {
    const next = !_ctrlState[key];

    if (key === "mic") {
      _ctrlState.mic = next;
      const vc = window._voiceClient;
      if (!vc) return;
      if (next) {
        await playGreeting();
        try {
          await vc._start();
        } catch (err) {
          console.error("[Mic] Erreur demarrage :", err);
          _ctrlState.mic = false;
          setOrbState("offline");
          setTimeout(() => setOrbState("idle"), 2000);
        }
      } else {
        vc._stop();
        setOrbState("idle");
      }
      return;
    }

    if (key === "cam") {
      if (next) {
        setCtrl("cam", true);  // marque actif immédiatement pour que le 2e clic puisse désactiver
        const ok = await startCamera();
        if (!ok) {
          setCtrl("cam", false);
          return;
        }
        J.api.patch("/api/permissions/camera", { enabled: true }).catch(() => {});
      } else {
        stopCamera();
        setCtrl("cam", false);
        J.api.patch("/api/permissions/camera", { enabled: false }).catch(() => {});
      }
      return;
    }

    if (key === "screen") {
      setCtrl("screen", next);
      J.api.patch("/api/permissions/screen", { enabled: next }).catch(() => {});
      return;
    }

    if (key === "files") {
      setCtrl("files", next);
      J.api.patch("/api/permissions/files", { enabled: next }).catch(() => {});
      return;
    }

    if (key === "music") {
      setCtrl("music", next);
      if (next) startMusicPoll();
      else stopMusicPoll();
      return;
    }

    if (key === "chat") {
      setCtrl("chat", next);
      if (next) loadChatWidget();
      return;
    }
  }

  // Charge l'etat initial des permissions depuis le serveur
  (async function loadPermissions() {
    try {
      const perms = await J.api.get("/api/permissions");
      if (perms.screen   != null) setCtrl("screen", perms.screen);
      if (perms.camera   != null) setCtrl("cam",    perms.camera);
      if (perms.files    != null) setCtrl("files",  perms.files);
    } catch (_) {}
  })();

  CTRL_DEFS.forEach(c => {
    const btn = document.getElementById(c.id);
    if (btn) btn.addEventListener("click", () => toggleCtrl(c.key));
  });

  // Lier le bouton mic au VoiceClient après DOMContentLoaded
  document.addEventListener("DOMContentLoaded", () => {
    const vc = window._voiceClient;
    if (vc) {
      vc._btn = document.getElementById("hc-mic");
    }
  }, { once: true });

  // ── Greeting vocal (comme l'ancien repo) ──────────────────────────
  async function playGreeting() {
    try {
      let fn = "";
      try {
        const s = await fetch("/api/wakeup/status").then((r) => r.json());
        fn = (s && s.user_firstname) || "";
      } catch { /* repli sans prénom */ }
      const greeting = fn ? `Systèmes en ligne. Bonjour ${fn}.` : "Systèmes en ligne.";
      const resp = await fetch("/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: greeting }),
      });
      const data = await resp.json();
      if (!data.audio_b64) return;

      // Décoder le base64 → ArrayBuffer → AudioContext
      const binary = atob(data.audio_b64);
      const bytes  = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      const audioCtx = new AudioContext();
      const buffer   = await audioCtx.decodeAudioData(bytes.buffer);
      const source   = audioCtx.createBufferSource();
      source.buffer  = buffer;
      source.connect(audioCtx.destination);

      setOrbState("speaking");

      await new Promise((resolve) => {
        source.onended = resolve;
        source.start();
      });
      audioCtx.close();
    } catch (err) {
      console.warn("[Greeting] Erreur :", err);
    } finally {
      setOrbState("listening");
    }
  }

  // ── Caméra (MediaPipe) ─────────────────────────────────────────────
  let _camStream = null;

  async function startCamera() {
    try {
      _camStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      });
      const video = document.getElementById("cam-video");
      if (video) {
        video.srcObject = _camStream;
        await video.play();
      }
      document.getElementById("cam-overlay")?.classList.add("is-open");
      // Initialise MediaPipe (charge les modèles si nécessaire)
      if (typeof mpInit === "function") {
        await mpInit();
        mpStart();
      }
      return true;
    } catch (err) {
      console.error("[Camera] Erreur :", err);
      return false;
    }
  }

  function stopCamera() {
    if (typeof mpStop === "function") mpStop();
    if (_camStream) {
      _camStream.getTracks().forEach(t => t.stop());
      _camStream = null;
    }
    const video = document.getElementById("cam-video");
    if (video) video.srcObject = null;
    document.getElementById("cam-overlay")?.classList.remove("is-open");
  }


  // ── Widget Musique ─────────────────────────────────────────────────
  let _musicPollTimer = null;
  let _musicPlaying   = false;

  function startMusicPoll() {
    fetchMusicStatus();
    _musicPollTimer = setInterval(fetchMusicStatus, 5000);
  }

  function stopMusicPoll() {
    clearInterval(_musicPollTimer);
    _musicPollTimer = null;
  }

  async function fetchMusicStatus() {
    try {
      const s = await J.api.get("/api/music/status");
      updateMusicWidget(s);
    } catch (_) {}
  }

  function updateMusicWidget(s) {
    const trackEl  = document.getElementById("hcw-music-track");
    const artistEl = document.getElementById("hcw-music-artist");
    const srcEl    = document.getElementById("hcw-music-source");
    const artEl    = document.getElementById("hcw-album-art");
    const fillEl   = document.getElementById("hcw-progress-fill");
    const playIcon = document.getElementById("hcw-play-icon");

    if (!s || !s.connected) {
      if (trackEl)  trackEl.textContent  = "Non connecté";
      if (artistEl) artistEl.textContent = s?.provider ? "Configurer dans les paramètres" : "Aucun service configuré";
      if (srcEl)    srcEl.textContent    = s?.provider || "—";
      return;
    }

    _musicPlaying = s.is_playing || false;

    const providerLabel = (s.provider || "").toUpperCase();
    if (srcEl) srcEl.textContent = providerLabel || "—";

    if (!s.track) {
      if (trackEl)  trackEl.textContent  = "Aucune lecture";
      if (artistEl) artistEl.textContent = providerLabel ? providerLabel + " CONNECTÉ" : "—";
    } else {
      if (trackEl)  trackEl.textContent  = s.track;
      if (artistEl) artistEl.textContent = s.last_played
        ? (s.artist || "") + (s.artist ? " — DERNIER JOUÉ" : "DERNIER JOUÉ")
        : (s.artist || "");
    }

    // Album art
    if (artEl) {
      if (s.album_art) {
        artEl.src = s.album_art;
        artEl.classList.add("loaded");
      } else {
        artEl.classList.remove("loaded");
      }
    }

    // Barre de progression
    if (fillEl && s.duration_ms > 0) {
      const pct = Math.min(100, (s.progress_ms / s.duration_ms) * 100);
      fillEl.style.width = pct + "%";
    }

    // Icône play/pause
    if (playIcon) {
      playIcon.innerHTML = _musicPlaying
        ? '<line x1="5" y1="2" x2="5" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="10" y1="2" x2="10" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        : '<path fill="currentColor" d="M3 2l10 4.5L3 11V2z"/>';
    }
  }

  // ── Spotify Web Playback SDK ───────────────────────────────────────
  let _spotifyPlayer   = null;
  let _spotifyDeviceId = null;
  let _sdkProgressTimer = null;
  let _currentTrackId  = null;

  async function fetchTrackBeat(trackId) {
    // Fallback immédiat — l'API audio-features est dépréciée pour les nouvelles apps
    const applyBeat = (tempo, energy) => { if (_orb) _orb.setMusicBeat(tempo, energy); };
    try {
      const { token } = await (await fetch("/api/spotify/token", { headers: J.authHeaders ? J.authHeaders() : {} })).json();
      if (!token) return applyBeat(120, 0.6);
      const resp = await fetch(
        `https://api.spotify.com/v1/audio-features/${trackId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!resp.ok) return applyBeat(120, 0.6);
      const f = await resp.json();
      applyBeat(f.tempo || 120, f.energy ?? 0.6);
    } catch (_) {
      applyBeat(120, 0.6);
    }
  }

  function _tickSDKProgress() {
    if (!_spotifyPlayer || !_musicPlaying) return;
    _spotifyPlayer.getCurrentState().then(state => {
      if (!state) return;
      const fillEl = document.getElementById("hcw-progress-fill");
      if (fillEl && state.duration) {
        fillEl.style.width = Math.min(100, (state.position / state.duration) * 100) + "%";
      }
    }).catch(() => {});
  }

  async function initSpotifySDK() {
    if (_spotifyPlayer || window._sdkInitStarted) return;
    window._sdkInitStarted = true;

    try {
      const status = await J.api.get("/api/music/provider-status");
      if (status.provider !== "spotify") return;
    } catch (_) { return; }

    window.onSpotifyWebPlaybackSDKReady = () => {
      _spotifyPlayer = new Spotify.Player({
        name: "FEDEX_V0",
        getOAuthToken: async (cb) => {
          try {
            const res = await fetch("/api/spotify/token", { headers: J.authHeaders ? J.authHeaders() : {} });
            const data = await res.json();
            cb(data.token || "");
          } catch (_) { cb(""); }
        },
        volume: 0.7,
      });

      _spotifyPlayer.addListener("ready", ({ device_id }) => {
        _spotifyDeviceId = device_id;
        // Enregistre le device sans transférer la lecture
        fetch("/api/spotify/transfer", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(J.authHeaders ? J.authHeaders() : {}) },
          body: JSON.stringify({ device_id }),
        }).catch(() => {});
        // Charge l'état initial (dernier joué)
        if (_ctrlState.music) fetchMusicStatus();
      });

      _spotifyPlayer.addListener("not_ready", () => {
        _spotifyDeviceId = null;
      });

      _spotifyPlayer.addListener("player_state_changed", (state) => {
        if (!state) return;
        const track = state.track_window?.current_track;
        if (!track) return;
        _musicPlaying = !state.paused;

        // Beat sync
        const tid = track.id;
        const wasPlaying = _musicPlaying;
        if (tid && (tid !== _currentTrackId || (!wasPlaying && !state.paused))) {
          _currentTrackId = tid;
          if (!state.paused) fetchTrackBeat(tid);
        }
        if (state.paused && _orb) _orb.setMusicBeat(0, 0);

        updateMusicWidget({
          connected: true,
          is_playing: !state.paused,
          track: track.name,
          artist: track.artists?.map(a => a.name).join(", ") || "",
          album: track.album?.name || "",
          album_art: track.album?.images?.[0]?.url || null,
          progress_ms: state.position,
          duration_ms: track.duration_ms,
          provider: "spotify",
        });
      });

      _spotifyPlayer.connect();
      _sdkProgressTimer = setInterval(_tickSDKProgress, 1000);
    };

    const script = document.createElement("script");
    script.src = "https://sdk.scdn.co/spotify-player.js";
    document.head.appendChild(script);
  }

  // Démarrage SDK au chargement de la page
  initSpotifySDK();

  // Boutons du widget musique — SDK en priorité, API en fallback
  document.getElementById("hcw-prev")?.addEventListener("click", () => {
    if (_spotifyPlayer) { _spotifyPlayer.previousTrack().catch(() => {}); return; }
    J.api.post("/api/music/prev").then(fetchMusicStatus).catch(() => {});
  });
  document.getElementById("hcw-play")?.addEventListener("click", () => {
    if (_spotifyPlayer) { _spotifyPlayer.togglePlay().catch(() => {}); return; }
    J.api.post(_musicPlaying ? "/api/music/pause" : "/api/music/play")
      .then(fetchMusicStatus).catch(() => {});
  });
  document.getElementById("hcw-next")?.addEventListener("click", () => {
    if (_spotifyPlayer) { _spotifyPlayer.nextTrack().catch(() => {}); return; }
    J.api.post("/api/music/next").then(fetchMusicStatus).catch(() => {});
  });


  // ── Widget Chat ────────────────────────────────────────────────────
  async function loadChatWidget() {
    const msgsEl  = document.getElementById("hcw-chat-msgs");
    const countEl = document.getElementById("hcw-chat-count");
    if (!msgsEl) return;
    try {
      const sessions = await J.api.get("/api/sessions");
      if (!sessions.length) {
        msgsEl.innerHTML = '<div class="hcw-empty">Aucune session</div>';
        return;
      }
      const msgs = await J.api.get("/api/sessions/" + sessions[0].id + "/messages?limit=30");
      if (countEl) countEl.textContent = msgs.length + " msg";
      msgsEl.innerHTML = "";
      const recent = msgs.slice(-14);
      if (!recent.length) {
        msgsEl.innerHTML = '<div class="hcw-empty">Aucun message</div>';
        return;
      }
      recent.forEach(m => {
        const text = m.content || m.text || "";
        if (!text) return;
        const wrap = document.createElement("div");
        wrap.className = "hcw-msg";
        const role = document.createElement("span");
        role.className = "hcw-msg-role " + (m.role === "assistant" ? "assistant" : "");
        role.textContent = m.role === "assistant" ? "FEDEX_V0" : "VOUS";
        const body = document.createElement("span");
        body.className = "hcw-msg-text";
        body.textContent = text.length > 220 ? text.slice(0, 217) + "…" : text;
        wrap.appendChild(role);
        wrap.appendChild(body);
        msgsEl.appendChild(wrap);
      });
      msgsEl.scrollTop = msgsEl.scrollHeight;
    } catch (_) {
      msgsEl.innerHTML = '<div class="hcw-empty">Erreur de chargement</div>';
    }
  }

  // ── Widget Chat : envoi de message texte ──────────────────────────
  let _chatSending = false;
  const GLOBEX_PENDING_KEY = "fedex_v0_globex_pending";
  const GLOBEX_APPROVE_YES = /^(oui|yes|ok|d['']accord|j\s*autorise|jautorise|approuve|approuver|vas[- ]?y|go|autorise)\b/i;
  const GLOBEX_APPROVE_NO = /^(non|no|refuse|refuser|annule|annuler|stop)\b/i;

  let _pendingAttachment = null;
  const CHAT_FILE_ACCEPT = /\.(txt|md|csv|xlsx|xls|pdf|png|jpe?g|webp)$/i;

  function getGlobexPending() {
    try {
      const raw = sessionStorage.getItem(GLOBEX_PENDING_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function setGlobexPending(pending) {
    if (pending) sessionStorage.setItem(GLOBEX_PENDING_KEY, JSON.stringify(pending));
    else sessionStorage.removeItem(GLOBEX_PENDING_KEY);
    updateGlobexPendingBanner();
  }

  function updateGlobexPendingBanner() {
    const input = document.getElementById("hcw-input");
    if (!input) return;
    const pending = getGlobexPending();
    if (pending) {
      input.placeholder = "Répondez oui / j'autorise ou non…";
      input.classList.add("hcw-input-pending");
    } else {
      input.placeholder = _pendingAttachment
        ? "Question sur le fichier… (Entrée pour envoyer)"
        : "Écrire à fedex-v0… (Ctrl+V image)";
      input.classList.remove("hcw-input-pending");
    }
    let banner = document.getElementById("hcw-globex-ws-banner");
    if (pending && pending.approval_id) {
      if (!banner) {
        banner = document.createElement("div");
        banner.id = "hcw-globex-ws-banner";
        banner.className = "hcw-globex-ws-banner";
        const chat = document.getElementById("hcw-chat");
        if (chat) chat.insertBefore(banner, chat.firstChild);
      }
      banner.innerHTML = "";
      banner.appendChild(document.createTextNode("Action en attente — aussi visible dans "));
      const link = document.createElement("a");
      link.href = "/dashboard";
      link.textContent = "Workspace → Initiatives";
      banner.appendChild(link);
      banner.hidden = false;
    } else if (banner) {
      banner.hidden = true;
    }
  }

  function clearPendingAttachment() {
    if (_pendingAttachment && _pendingAttachment.previewUrl) {
      URL.revokeObjectURL(_pendingAttachment.previewUrl);
    }
    _pendingAttachment = null;
    const bar = document.getElementById("hcw-attach-bar");
    const attachBtn = document.getElementById("hcw-attach");
    const thumb = document.getElementById("hcw-attach-thumb");
    if (bar) bar.hidden = true;
    if (attachBtn) attachBtn.classList.remove("has-file");
    if (thumb) {
      thumb.hidden = true;
      thumb.style.backgroundImage = "";
    }
    const fileInput = document.getElementById("hcw-file-input");
    if (fileInput) fileInput.value = "";
    updateGlobexPendingBanner();
  }

  function setPendingAttachment(file) {
    if (!file) return;
    clearPendingAttachment();
    const previewUrl = file.type && file.type.startsWith("image/")
      ? URL.createObjectURL(file)
      : null;
    _pendingAttachment = { file, previewUrl };
    const bar = document.getElementById("hcw-attach-bar");
    const nameEl = document.getElementById("hcw-attach-name");
    const thumb = document.getElementById("hcw-attach-thumb");
    const attachBtn = document.getElementById("hcw-attach");
    if (nameEl) nameEl.textContent = file.name || "fichier";
    if (bar) bar.hidden = false;
    if (attachBtn) attachBtn.classList.add("has-file");
    if (thumb && previewUrl) {
      thumb.hidden = false;
      thumb.style.backgroundImage = "url(" + previewUrl + ")";
    }
    updateGlobexPendingBanner();
    document.getElementById("hcw-input")?.focus();
  }

  function fileFromClipboardItem(item) {
    if (!item || !item.type) return null;
    if (item.type.startsWith("image/")) {
      const blob = item.getAsFile();
      if (!blob) return null;
      const ext = item.type.split("/")[1] === "jpeg" ? "jpg" : item.type.split("/")[1] || "png";
      return new File([blob], "image-collee." + ext, { type: item.type });
    }
    return null;
  }

  function handleChatPaste(e) {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      const file = fileFromClipboardItem(items[i]);
      if (file) {
        e.preventDefault();
        setPendingAttachment(file);
        return;
      }
    }
  }

  function pickChatFile(file) {
    if (!file) return;
    const name = (file.name || "").toLowerCase();
    const mime = (file.type || "").toLowerCase();
    const allowedMime =
      mime.startsWith("image/") ||
      mime === "application/pdf" ||
      mime.includes("spreadsheet") ||
      mime.includes("excel") ||
      mime === "text/plain" ||
      mime === "text/csv" ||
      mime === "text/markdown";
    if (!allowedMime && !CHAT_FILE_ACCEPT.test(name)) {
      J.notify?.({ kind: "err", text: "Type non supporté (image, PDF, Excel, txt…)" });
      return;
    }
    setPendingAttachment(file);
  }

  async function sendAssistantFileMessage(file, question, streamTarget) {
    const q =
      (question || "").trim() ||
      "Lis ce fichier (OCR si image) et résume le contenu en français.";
    const form = new FormData();
    form.append("file", file);
    form.append("question", q);

    const resp = await fetch("/api/assistant/ask-with-file", {
      method: "POST",
      headers: J.authHeaders ? J.authHeaders() : {},
      body: form,
    });
    let data = {};
    try {
      data = await resp.json();
    } catch (_) {
      data = {};
    }
    if (!resp.ok) {
      let detail = data.detail || data.message || "Erreur analyse fichier";
      if (resp.status === 405) {
        detail = "Service fichier indisponible — redémarrez fedex-v0 (port 8011) puis réessayez.";
      } else if (typeof detail !== "string" && Array.isArray(detail)) {
        detail = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
      } else if (typeof detail !== "string") {
        detail = JSON.stringify(detail);
      }
      throw new Error(detail);
    }
    let reply = data.reply || "Pas de réponse.";
    if (data.warnings && data.warnings.length) {
      reply += "\n\n_" + data.warnings.join(" — ") + "_";
    }
    if (streamTarget) streamTarget.textContent = reply;
    setOrbState("speaking");
    return data;
  }

  function appendChatMsg(role, text, streaming) {
    const msgsEl = document.getElementById("hcw-chat-msgs");
    if (!msgsEl) return null;
    const empty = msgsEl.querySelector(".hcw-empty");
    if (empty) empty.remove();

    const wrap = document.createElement("div");
    wrap.className = "hcw-msg";
    const roleEl = document.createElement("span");
    roleEl.className = "hcw-msg-role" + (role === "assistant" ? " assistant" : "");
    roleEl.textContent = role === "assistant" ? "FEDEX_V0" : "VOUS";
    const bodyEl = document.createElement("span");
    bodyEl.className = "hcw-msg-text";
    bodyEl.textContent = text;
    wrap.appendChild(roleEl);
    wrap.appendChild(bodyEl);
    msgsEl.appendChild(wrap);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    if (streaming) return bodyEl;
    return null;
  }

  function globexApiOrigin() {
    if (location.port === "8010") {
      return location.protocol + "//" + location.hostname + ":8011";
    }
    return "";
  }

  function buildGlobexExportUrl(spec) {
    if (!spec || !spec.preset) return "#";
    const params = new URLSearchParams();
    params.set("preset", spec.preset);
    params.set("filename", spec.filename || "export.pdf");
    params.set("format", spec.format || "pdf");
    if (spec.limit != null) params.set("limit", String(spec.limit));
    if (spec.records != null) params.set("limit", String(spec.records));
    if (spec.module) params.set("module", spec.module);
    if (spec.export_token) params.set("export_token", spec.export_token);
    if (spec.hours != null) params.set("hours", String(spec.hours));
    if (spec.tracking_numbers) params.set("tracking_numbers", spec.tracking_numbers);
    return globexApiOrigin() + "/api/globex/export/download?" + params.toString();
  }

  async function downloadGlobexExport(spec, opts) {
    const options = opts || {};
    if (!spec || !spec.preset) return false;
    const url = buildGlobexExportUrl(spec);
    const fname = spec.filename || "export.pdf";

    // Méthode 1 : iframe masquée — fonctionne sans clic utilisateur (Chrome, Firefox, Opera)
    if (options.preferIframe !== false) {
      try {
        const iframe = document.createElement("iframe");
        iframe.setAttribute("aria-hidden", "true");
        iframe.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;border:0;opacity:0";
        iframe.src = url;
        document.body.appendChild(iframe);
        setTimeout(() => iframe.remove(), 120000);
        return true;
      } catch (err) {
        console.warn("Globex iframe download failed", err);
      }
    }

    // Méthode 2 : fetch + blob (clic utilisateur sur la carte)
    try {
      const resp = await fetch(url, { headers: J.authHeaders ? J.authHeaders() : {} });
      if (!resp.ok) {
        const err = await resp.text();
        throw new Error(err || `HTTP ${resp.status}`);
      }
      const ctype = (resp.headers.get("content-type") || "").toLowerCase();
      if (ctype.includes("json") || ctype.includes("text/html")) {
        const errBody = await resp.text();
        throw new Error(errBody.slice(0, 200) || "Réponse invalide (pas un PDF)");
      }
      const blob = await resp.blob();
      if (!blob || blob.size < 32) {
        throw new Error("Fichier vide — vérifiez http://127.0.0.1:8011");
      }
      const blobUrl = URL.createObjectURL(blob);
      const dl = document.createElement("a");
      dl.href = blobUrl;
      dl.download = fname;
      dl.style.display = "none";
      document.body.appendChild(dl);
      dl.click();
      dl.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
      return true;
    } catch (err) {
      console.warn("Globex blob download failed", err);
      return false;
    }
  }

  const GLOBEX_EXPORT_CACHE_KEY = "fedex_v0_last_export_download";

  function exportFileKindLabel(spec) {
    const fmt = String((spec && spec.format) || "pdf").toLowerCase();
    return fmt === "xlsx" ? "Excel" : "PDF";
  }

  function clearStaleExportCache() {
    try {
      sessionStorage.removeItem(GLOBEX_EXPORT_CACHE_KEY);
    } catch (_) {
      /* ignore */
    }
  }

  function isExportSpecDownloadable(spec) {
    if (!spec || !spec.preset) return false;
    if (spec.preset === "admin_logs") return spec.hours != null;
    if (spec.preset === "admin_generic" || spec.module === "text") return !!spec.export_token;
    return true;
  }

  function cacheExportDownload(spec) {
    if (!spec || !spec.preset) return;
    try {
      sessionStorage.setItem(GLOBEX_EXPORT_CACHE_KEY, JSON.stringify(spec));
    } catch (_) {
      /* ignore */
    }
  }

  function readCachedExportDownload() {
    try {
      const raw = sessionStorage.getItem(GLOBEX_EXPORT_CACHE_KEY);
      if (!raw) return null;
      const spec = JSON.parse(raw);
      return isExportSpecDownloadable(spec) ? spec : null;
    } catch (_) {
      return null;
    }
  }

  function resolveExportSpec(data) {
    if (data && data.export_download && data.export_download.preset) {
      cacheExportDownload(data.export_download);
      return data.export_download;
    }
    const cached = readCachedExportDownload();
    if (cached) return cached;
    const inferred = inferExportSpecFromResponse(data);
    return isExportSpecDownloadable(inferred) ? inferred : null;
  }

  const EXPORT_TOOL_PRESETS = {
    generate_text_pdf: { preset: "admin_generic", format: "pdf", module: "text" },
    export_activity_logs_pdf: { preset: "admin_logs", format: "pdf", hoursKey: true },
    export_activity_logs_excel: { preset: "admin_logs", format: "xlsx", hoursKey: true },
    export_notifications_pdf: { preset: "admin_notifications", module: "notifications" },
    export_users_pdf: { preset: "admin_users", module: "users" },
    export_tracking_pdf: { preset: "admin_tracking", module: "tracking" },
    export_tickets_pdf: { preset: "admin_tickets", module: "tickets" },
    export_conversations_pdf: { preset: "admin_conversations", module: "conversations" },
  };

  function inferExportSpecFromResponse(data) {
    if (data.export_download && data.export_download.preset) {
      return data.export_download;
    }
    const tools = data.tools_used || [];
    const reply = data.reply || "";
    for (let i = 0; i < tools.length; i++) {
      const tool = tools[i];
      const meta = EXPORT_TOOL_PRESETS[tool];
      if (!meta) continue;
      const fnameMatch = reply.match(/([\w.-]+\.(?:pdf|xlsx))/i);
      const hoursMatch =
        reply.match(/activity-logs-(\d+)h/i) ||
        reply.match(/sur\s+(?:les\s+)?(\d+)\s*h/i) ||
        reply.match(/(\d+)\s*h(?:eures?)?/i);
      const spec = {
        preset: meta.preset,
        format: meta.format || "pdf",
        filename: fnameMatch ? fnameMatch[1] : "export.pdf",
      };
      if (meta.hoursKey) {
        spec.hours = hoursMatch ? parseInt(hoursMatch[1], 10) : 24;
        if (!fnameMatch) spec.filename = "activity-logs-" + spec.hours + "h.pdf";
      }
      if (meta.module) spec.module = meta.module;
      if (!isExportSpecDownloadable(spec)) return null;
      return spec;
    }
    const fnameOnly = reply.match(/activity-logs-(\d+)h\.pdf/i);
    if (fnameOnly || /export\s+pdf\s+pr[eê]t/i.test(reply)) {
      const hours = fnameOnly ? parseInt(fnameOnly[1], 10) : 24;
      const fn = fnameOnly ? fnameOnly[0] : "activity-logs-" + hours + "h.pdf";
      return { preset: "admin_logs", format: "pdf", filename: fn, hours: hours };
    }
    return null;
  }

  function cleanExportReplyText(reply) {
    if (!reply) return reply;
    return reply
      .split("\n")
      .filter((ln) => !/t[eé]l[eé]chargez\s*:/i.test(ln))
      .filter((ln) => !/voici le (pdf|excel|fichier)\s*:/i.test(ln))
      .map((ln) => ln.replace(/\*\*([^*]+)\*\*/g, "$1"))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function appendGlobexExportInlineLink(msgWrap, spec) {
    if (!msgWrap || !spec || !spec.preset) return;
    if (!isExportSpecDownloadable(spec)) {
      const warn = document.createElement("p");
      warn.className = "hcw-export-inline-line hcw-export-warn";
      warn.textContent =
        "Export détecté mais lien indisponible. Rechargez avec Ctrl+F5 sur http://127.0.0.1:8011 puis regénérez le PDF.";
      const inline = document.createElement("div");
      inline.className = "hcw-export-inline";
      inline.appendChild(warn);
      msgWrap.appendChild(inline);
      return;
    }

    msgWrap.querySelectorAll(".hcw-export-inline, .hcw-export-card").forEach((el) => el.remove());

    const url = buildGlobexExportUrl(spec);
    const fname = spec.filename || "export.pdf";

    const inline = document.createElement("div");
    inline.className = "hcw-export-inline";

    const line = document.createElement("p");
    line.className = "hcw-export-inline-line";

    const prefix = document.createTextNode("Voici le " + exportFileKindLabel(spec) + " : ");
    const a = document.createElement("a");
    a.className = "hcw-export-dl-link";
    a.href = "#";
    a.setAttribute("role", "button");
    a.download = fname;
    a.textContent = "Télécharger " + fname;
    a.title = "Télécharger le fichier";

    a.addEventListener("click", async (e) => {
      e.preventDefault();
      a.textContent = "Téléchargement…";
      const ok = await downloadGlobexExport(spec, { preferIframe: false });
      if (!ok) {
        a.textContent = "Échec — ouvrez le port 8011";
        a.style.color = "#ff8a8a";
        return;
      }
      a.textContent = "Télécharger " + fname;
    });

    line.appendChild(prefix);
    line.appendChild(a);
    inline.appendChild(line);
    msgWrap.appendChild(inline);
  }

  function appendGlobexExportCard(msgWrap, spec, opts) {
    const options = opts || {};
    if (!msgWrap || !spec || !spec.preset) return;

    msgWrap.querySelectorAll(".hcw-export-card").forEach((el) => el.remove());

    const fname = spec.filename || "export.pdf";
    const fmt = String(spec.format || "pdf").toUpperCase();

    const card = document.createElement("div");
    card.className = "hcw-export-card";
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    card.title = "Cliquer pour télécharger " + fname;

    const icon = document.createElement("span");
    icon.className = "hcw-export-icon";
    icon.textContent = "📄";

    const meta = document.createElement("div");
    meta.className = "hcw-export-meta";

    const link = document.createElement("span");
    link.className = "hcw-export-link";
    link.textContent = fname;

    const sub = document.createElement("span");
    sub.className = "hcw-export-sub";
    sub.textContent = fmt + " — téléchargement automatique…";

    meta.appendChild(link);
    meta.appendChild(sub);
    card.appendChild(icon);
    card.appendChild(meta);

    const triggerDownload = (e, dlOpts) => {
      const o = dlOpts || {};
      if (e && e.preventDefault) e.preventDefault();
      if (e && e.stopPropagation) e.stopPropagation();
      card.classList.add("hcw-export-card-loading");
      sub.textContent = "Téléchargement…";
      const preferIframe = o.preferIframe !== false && !o.userClick;
      return downloadGlobexExport(spec, { preferIframe: preferIframe, userClick: !!o.userClick }).then((ok) => {
        card.classList.remove("hcw-export-card-loading");
        sub.textContent = ok ? "Téléchargé ✓ — recliquez si besoin" : "Échec — cliquez pour réessayer";
        return ok;
      });
    };

    card.addEventListener("click", (e) => triggerDownload(e, { userClick: true, preferIframe: false }));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") triggerDownload(e, { userClick: true, preferIframe: false });
    });

    msgWrap.appendChild(card);

    if (options.autoDownload !== false) {
      triggerDownload(null, { preferIframe: true });
    }
  }

  async function resolveGlobexApproval(approvalId, approved, actionsEl, hintEl, opts) {
    const options = opts || {};
    const path = approved ? "approve" : "reject";
    try {
      const resp = await fetch(`/api/globex/${path}/${approvalId}`, {
        method: "POST",
        headers: J.authHeaders ? J.authHeaders() : {},
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || `HTTP ${resp.status}`);
      }
      setGlobexPending(null);
      const replyText = approved
        ? (data.reply || "✅ Action approuvée et exécutée.")
        : (data.reply || "❌ Action refusée — rien n'a été modifié.");

      if (actionsEl) actionsEl.innerHTML = "";
      if (options.streamTarget) {
        options.streamTarget.textContent = replyText;
      } else if (options.followUpBubble) {
        appendChatMsg("assistant", replyText, false);
      } else if (hintEl) {
        hintEl.textContent = replyText;
      }
      return data;
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      if (options.streamTarget) options.streamTarget.textContent = "Erreur approbation : " + msg;
      else alert("Approbation : " + msg);
      return null;
    }
  }

  function formatGlobexReply(data) {
    let reply = (data.reply || "").trim();
    if (!reply) reply = "Réponse vide du serveur Globex.";
    if (data.needs_approval && data.approval_id) {
      const hint = data.approval_hint ? String(data.approval_hint) : "Action sensible en attente.";
      reply += `\n\n⏸ ${hint}`;
      reply += "\n\nRépondez **oui** / **j'autorise** pour exécuter, **non** pour annuler — ou utilisez les boutons ci-dessous.";
    }
    return reply;
  }

  function renderGlobexMessageExtras(msgWrap, data, opts) {
    const options = opts || {};
    if (!msgWrap || !data) return;
    let actions = msgWrap.querySelector(".hcw-msg-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "hcw-msg-actions";
      msgWrap.appendChild(actions);
    }
    actions.innerHTML = "";

    if (data.export_download && data.export_download.preset) {
      cacheExportDownload(data.export_download);
    } else if (!(data.tools_used || []).some((t) => /export|generate_text_pdf/i.test(t))) {
      clearStaleExportCache();
    }

    const exportSpec = resolveExportSpec(data);
    if (exportSpec) {
      appendGlobexExportInlineLink(msgWrap, exportSpec);
    }

    if (data.needs_approval && data.approval_id) {
      const hint = msgWrap.querySelector(".hcw-msg-text");
      const approveBtn = document.createElement("button");
      approveBtn.type = "button";
      approveBtn.className = "hcw-action-btn approve";
      approveBtn.textContent = "Approuver";
      approveBtn.addEventListener("click", async () => {
        await resolveGlobexApproval(data.approval_id, true, actions, hint, { followUpBubble: true });
      });
      const rejectBtn = document.createElement("button");
      rejectBtn.type = "button";
      rejectBtn.className = "hcw-action-btn reject";
      rejectBtn.textContent = "Refuser";
      rejectBtn.addEventListener("click", async () => {
        await resolveGlobexApproval(data.approval_id, false, actions, hint, { followUpBubble: true });
      });
      actions.appendChild(approveBtn);
      actions.appendChild(rejectBtn);

      const wsBtn = document.createElement("a");
      wsBtn.className = "hcw-action-btn ws-link";
      wsBtn.href = "/dashboard";
      wsBtn.textContent = "Workspace";
      wsBtn.title = "Voir dans le pilotage Workspace";
      actions.appendChild(wsBtn);

      setGlobexPending({
        approval_id: data.approval_id,
        hint: data.approval_hint || "",
      });
    } else if (!getGlobexPending() || !data.needs_approval) {
      setGlobexPending(null);
    }
  }

  async function handleGlobexPendingChat(text, streamTarget) {
    const pending = getGlobexPending();
    if (!pending || !pending.approval_id) return false;

    const trimmed = text.trim();
    let approved = null;
    if (GLOBEX_APPROVE_YES.test(trimmed)) approved = true;
    else if (GLOBEX_APPROVE_NO.test(trimmed)) approved = false;

    if (approved === null) {
      if (streamTarget) {
        streamTarget.textContent =
          "⏸ Toujours en attente de votre décision.\nRépondez **oui** / **j'autorise** pour exécuter, **non** pour annuler — ou utilisez les boutons sur le message précédent.";
      }
      return true;
    }

    await resolveGlobexApproval(pending.approval_id, approved, null, null, {
      streamTarget: streamTarget,
    });
    return true;
  }

  function collectGlobexHistory(maxTurns) {
    const limit = maxTurns || 12;
    const msgsEl = document.getElementById("hcw-chat-msgs");
    if (!msgsEl) return [];
    const out = [];
    msgsEl.querySelectorAll(".hcw-msg").forEach((wrap) => {
      const roleEl = wrap.querySelector(".hcw-msg-role");
      const textEl = wrap.querySelector(".hcw-msg-text");
      if (!roleEl || !textEl) return;
      const content = (textEl.textContent || "").trim();
      if (!content || content === "fedex-v0 réfléchit…") return;
      const role = roleEl.classList.contains("assistant") ? "assistant" : "user";
      out.push({ role, content });
    });
    return out.slice(-limit);
  }

  async function sendGlobexChatMessage(text, streamTarget) {
    const looksExport = /\b(pdf|export|exporter|g[eé]n[eè]re|g[eé]nere|t[eé]l[eé]charger|fichier)\b/i.test(text);
    const thinkStarted = Date.now();
    if (streamTarget && looksExport) {
      streamTarget.textContent = "fedex-v0 prépare le fichier…";
      setOrbState("thinking");
    }

    const resp = await fetch("/api/globex/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(J.authHeaders ? J.authHeaders() : {}) },
      body: JSON.stringify({
        message: text,
        agent_mode: true,
        ui_language: "fr",
        conversation_history: collectGlobexHistory(),
      }),
    });
    let data = {};
    try {
      data = await resp.json();
    } catch (_) {
      data = {};
    }
    if (!resp.ok) {
      const detail = data.detail || data.message || `Erreur Globex (${resp.status})`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    if (looksExport) {
      const minMs = 650;
      const elapsed = Date.now() - thinkStarted;
      if (elapsed < minMs) {
        await new Promise((resolve) => setTimeout(resolve, minMs - elapsed));
      }
    }

    if (data.export_download && data.export_download.preset) {
      cacheExportDownload(data.export_download);
    }

    const reply = formatGlobexReply(data);
    if (streamTarget) {
      const spec = resolveExportSpec(data);
      streamTarget.textContent = spec ? cleanExportReplyText(reply) : reply;
      const msgWrap = streamTarget.closest(".hcw-msg");
      renderGlobexMessageExtras(msgWrap, data, { autoDownload: false });
    }
    setOrbState("speaking");
    return data;
  }

  async function sendChatMessage() {
    if (_chatSending) return;
    const input = document.getElementById("hcw-input");
    const sendBtn = document.getElementById("hcw-send");
    const text = (input?.value || "").trim();
    const attachment = _pendingAttachment;
    if (!text && !attachment) return;

    _chatSending = true;
    if (sendBtn) sendBtn.disabled = true;
    input.value = "";
    if (attachment) clearPendingAttachment();

    const userLabel = attachment
      ? (text ? text + "\n📎 " + attachment.file.name : "📎 " + attachment.file.name)
      : text;
    appendChatMsg("user", userLabel, false);

    const streamTarget = appendChatMsg("assistant", "fedex-v0 réfléchit…", true);
    setOrbState("thinking");

    const useGlobex = window.GLOBEX_OS_ENABLED === true;

    try {
      if (attachment) {
        await sendAssistantFileMessage(attachment.file, text, streamTarget);
      } else if (useGlobex) {
        const handled = await handleGlobexPendingChat(text, streamTarget);
        if (!handled) {
          await sendGlobexChatMessage(text, streamTarget);
        }
      } else {
      const sessionId = localStorage.getItem("fedex_v0_voice_session") || null;
      const resp = await fetch("/api/voice/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(J.authHeaders ? J.authHeaders() : {}) },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const returnedSid = resp.headers.get("x-session-id");
      if (returnedSid) localStorage.setItem("fedex_v0_voice_session", returnedSid);

      if (!resp.ok || !resp.body) throw new Error("Erreur réseau");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let full = "";
      setOrbState("speaking");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        if (streamTarget) {
          streamTarget.textContent = full || "fedex-v0 réfléchit…";
          document.getElementById("hcw-chat-msgs").scrollTop = 9999;
        }
      }

      if (!full.trim() && streamTarget) {
        streamTarget.textContent =
          "Pas de réponse (Ollama indisponible ou timeout). Activez GLOBEX_OS_ENABLED=true pour utiliser Globex FedEx.";
      }
      }

      const countEl = document.getElementById("hcw-chat-count");
      if (countEl) {
        const cur = parseInt(countEl.textContent) || 0;
        countEl.textContent = (cur + 2) + " msg";
      }
    } catch (err) {
      const msg = err && err.message ? err.message : "Erreur de communication.";
      if (streamTarget) streamTarget.textContent = msg;
    } finally {
      _chatSending = false;
      if (sendBtn) sendBtn.disabled = false;
      setTimeout(() => setOrbState("idle"), 1200);
    }
  }

  document.getElementById("hcw-new-session")?.addEventListener("click", () => {
    localStorage.removeItem("fedex_v0_voice_session");
    setGlobexPending(null);
    clearPendingAttachment();
    const msgsEl  = document.getElementById("hcw-chat-msgs");
    const countEl = document.getElementById("hcw-chat-count");
    if (msgsEl)  msgsEl.innerHTML = '<div class="hcw-empty">Nouvelle conversation</div>';
    if (countEl) countEl.textContent = "—";
    document.getElementById("hcw-input")?.focus();
  });

  document.getElementById("hcw-send")?.addEventListener("click", sendChatMessage);

  document.getElementById("hcw-attach")?.addEventListener("click", () => {
    document.getElementById("hcw-file-input")?.click();
  });

  document.getElementById("hcw-file-input")?.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    pickChatFile(file);
  });

  document.getElementById("hcw-attach-remove")?.addEventListener("click", () => {
    clearPendingAttachment();
  });

  const chatWidget = document.getElementById("hc-widget-chat");
  chatWidget?.addEventListener("paste", handleChatPaste);
  chatWidget?.addEventListener("dragover", (e) => {
    if (e.dataTransfer && e.dataTransfer.types && e.dataTransfer.types.includes("Files")) {
      e.preventDefault();
    }
  });
  chatWidget?.addEventListener("drop", (e) => {
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) {
      e.preventDefault();
      pickChatFile(file);
    }
  });

  document.getElementById("hcw-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  window.addEventListener("fedex_v0:ws", (e) => {
    const msg = e.detail;
    if (!msg || !msg.type) return;
    if (msg.type === "globex_pending" && msg.approval_id) {
      setGlobexPending({ approval_id: msg.approval_id, hint: msg.hint || "" });
    }
    if (msg.type === "globex_pending_clear") {
      setGlobexPending(null);
    }
    if (msg.type === "globex_export" && msg.export_download) {
      const msgsEl = document.getElementById("hcw-chat-msgs");
      const lastMsg = msgsEl && msgsEl.querySelector(".hcw-msg:last-child");
      if (lastMsg) {
        appendGlobexExportInlineLink(lastMsg, msg.export_download);
      }
    }
  });

  updateGlobexPendingBanner();


  // ── WebSocket — sync état orbe + canal passif ──────────────────────
  function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    try {
      _ws = new WebSocket(proto + "//" + location.host + "/ws");
    } catch (_) { return; }

    _ws.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch (_) { return; }

      if (data.type === "voice_state") setOrbState(data.state || "idle");
      if (data.type === "audio_level" && _orb) _orb.setAudioLevel(data.level || 0);
      if (data.type === "wake_up") window.dispatchEvent(new CustomEvent("fedex_v0-wake", { detail: data }));

      if (data.type === "message" && data.role === "assistant" && data.text) {
        showChannel(data.text);
        if (_ctrlState.chat) loadChatWidget();
      }

      // ── View routing ──────────────────────────────────────────────
      if (data.type === "reload_views") {
        const _prevActive = J.views._active;
        if (_prevActive) J.views.deactivate(_prevActive);
        // Supprime aussi les scripts sans data-view-skill (chargés avant le fix)
        document.querySelectorAll('script[src*="/skills/"]').forEach(el => el.remove());
        document.querySelectorAll('link[href*="/skills/"]').forEach(el => el.remove());
        window.loadViewSkills?.().then?.(() => {
          if (_prevActive) J.views.activate(_prevActive);
        });
      }
      if (data.type === "show_home")  { const a = J.views._active; if (a) J.views.deactivate(a); }
      if (data.type === "show_view")    J.views.activate(data.view_id, data.params);
      if (data.type === "hide_view")    J.views.deactivate(data.view_id);
      if (data.type === "view_command") J.views.dispatch(data.view_id, data.command, data.params);

      // Backward compat (map_control legacy events)
      if (data.type === "map_fly_to")    { J.views.activate("globe"); J.views.dispatch("globe", "fly_to", data); }
      if (data.type === "map_zoom_out")  J.views.dispatch("globe", "zoom_out", {});
      if (data.type === "map_zoom_in")   J.views.dispatch("globe", "zoom_in", {});
      if (data.type === "map_globe_view"){ J.views.activate("globe"); J.views.dispatch("globe", "globe_view", {}); }
      if (data.type === "toggle_panels") J.views.dispatch("globe", "toggle_panels", {});
    };

    _ws.onclose = () => setTimeout(connectWS, 3000);
  }
  connectWS();

  // ── Canal passif (bas-droite) ──────────────────────────────────────
  let _channelTs    = null;
  let _channelTimer = null;

  function relativeTime(ts) {
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 1)  return "À L'INSTANT";
    if (mins === 1) return "IL Y A 1 MIN";
    if (mins < 60) return "IL Y A " + mins + " MIN";
    return "IL Y A " + Math.floor(mins / 60) + " H";
  }

  function updateChannelTime() {
    if (!_channelTs) return;
    const el = document.getElementById("channel-time");
    if (el) el.textContent = relativeTime(_channelTs);
  }

  function showChannel(text) {
    const el  = document.getElementById("home-channel");
    const msg = document.getElementById("channel-msg");
    if (!el || !msg) return;
    msg.textContent = text.length > 160 ? text.slice(0, 157) + "…" : text;
    _channelTs = Date.now();
    updateChannelTime();
    el.style.display = "";
    if (_channelTimer) clearInterval(_channelTimer);
    _channelTimer = setInterval(updateChannelTime, 30000);
  }

  (async function loadLastMessage() {
    try {
      const sessions = await J.api.get("/api/sessions");
      if (!sessions.length) return;
      const msgs = await J.api.get("/api/sessions/" + sessions[0].id + "/messages?limit=10");
      const last = [...msgs].reverse().find(m => m.role === "assistant");
      if (last && (last.content || last.text)) showChannel(last.content || last.text);
    } catch (_) {}
  })();

  // ── Navigation iframe — shell persistant ─────────────────────────
  const _frame = document.getElementById("page-frame");
  let _frameActive = false;

  fedexV0.navigateFrame = function (url) {
    if (!url || url === "/" || url === window.location.origin + "/") {
      // Retour home — cacher l'iframe
      if (_frame) {
        _frame.classList.remove("is-active");
        _frame.src = "about:blank";
      }
      _frameActive = false;
      history.replaceState(null, "", "/");
    } else {
      // Fermer toute vue active (globe, etc.) avant de naviguer
      fedexV0.views.deactivate();
      if (_frame) {
        _frame.src = url;
        _frame.classList.add("is-active");
      }
      _frameActive = true;
      history.pushState({ frame: url }, "", url);
    }
  };

  // Bouton retour navigateur
  window.addEventListener("popstate", (e) => {
    if (e.state?.frame) {
      if (_frame) { _frame.src = e.state.frame; _frame.classList.add("is-active"); }
      _frameActive = true;
    } else {
      if (_frame) { _frame.classList.remove("is-active"); _frame.src = "about:blank"; }
      _frameActive = false;
    }
  });

  // ── Touche espace → dashboard (ou ferme l'iframe si déjà ouvert) ──
  document.addEventListener("keydown", (e) => {
    if (e.key === " " && !e.metaKey && !e.ctrlKey) {
      const active = document.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
      e.preventDefault();
      if (_frameActive) {
        fedexV0.navigateFrame("/");
      } else {
        fedexV0.navigateFrame("/dashboard");
      }
    }
  });

  // ── Helper drag-and-drop pour widgets / overlay ────────────────────
  function makeDraggable(el, handle) {
    if (!el) return;
    const grip = handle || el;

    grip.addEventListener("mousedown", (e) => {
      if (e.target.closest("button, input, textarea, .hcw-resize-handle")) return;
      e.preventDefault();
      let ex = e.clientX, ey = e.clientY;
      el.classList.add("dragging");

      function onMove(e) {
        const dx = e.clientX - ex;
        const dy = e.clientY - ey;
        ex = e.clientX; ey = e.clientY;
        const rect = el.getBoundingClientRect();
        el.style.left   = (rect.left + dx) + "px";
        el.style.top    = (rect.top  + dy) + "px";
        el.style.right  = "auto";
        el.style.bottom = "auto";
      }

      function onUp() {
        el.classList.remove("dragging");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup",   onUp);
      }

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup",   onUp);
    });
  }

  // ── Helper redimensionnement pour widgets ──────────────────────────
  function makeResizable(el, handleEl, minW, minH) {
    if (!el || !handleEl) return;
    minW = minW || 180;
    minH = minH || 80;

    handleEl.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();

      // Ancrer en top/left au moment du resize
      const rect = el.getBoundingClientRect();
      el.style.left   = rect.left   + "px";
      el.style.top    = rect.top    + "px";
      el.style.right  = "auto";
      el.style.bottom = "auto";
      el.style.width  = rect.width  + "px";
      el.style.height = rect.height + "px";

      const startX = e.clientX;
      const startY = e.clientY;
      const startW = rect.width;
      const startH = rect.height;

      function onMove(e) {
        const w = Math.max(minW, startW + (e.clientX - startX));
        const h = Math.max(minH, startH + (e.clientY - startY));
        el.style.width  = w + "px";
        el.style.height = h + "px";
        // Enleve max-height sur le corps messages si present
        const msgs = el.querySelector(".hcw-messages");
        if (msgs) msgs.style.maxHeight = "none";
      }

      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup",   onUp);
      }

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup",   onUp);
    });
  }

  // Attacher drag + resize aux widgets
  makeDraggable(document.getElementById("cam-overlay"), document.getElementById("cam-drag-handle"));
  makeResizable(document.getElementById("cam-overlay"), document.getElementById("cam-resize-handle"), 180, 120);

  makeDraggable(document.getElementById("hc-widget-music"));
  makeResizable(document.getElementById("hc-widget-music"), document.getElementById("music-resize-handle"), 180, 100);

  makeDraggable(document.getElementById("hc-widget-chat"));
  makeResizable(document.getElementById("hc-widget-chat"), document.getElementById("chat-resize-handle"), 220, 160);
})();
