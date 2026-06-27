/* dashboard.js — Workspace (Pilotage) v2
 * 5 sous-pages : Aperçu · Initiatives · Missions · Tâches · Analytics
 */
(function () {
  "use strict";
  const J = window.Jarvis, el = J.el;

  const PAGES = [
    { id: "apercu",      label: "Aperçu" },
    { id: "initiatives", label: "Initiatives" },
    { id: "missions",    label: "Missions" },
    { id: "taches",      label: "Tâches" },
    { id: "analytics",   label: "Analytics" },
  ];

  let _activePage = "apercu";
  const root = document.getElementById("page-root");


  /* ───────── Constantes PHASE 6 §10.1 ───────── */
  const AUTONOMY_LABELS = {
    0: "RESPOND_ONLY", 1: "SUGGEST", 2: "DRAFT",
    3: "SANDBOX", 4: "MODIFY_PROJECT", 5: "EXTERNAL_ACTION",
  };

  const PATCH_LABELS = {
    archive_fact:           "Fact à archiver",
    mark_skill_stale:       "Skill peu utilisée",
    archive_skill:          "Skill obsolète",
    reject_stale_candidate: "Candidate en attente",
    review_contradiction:   "Contradictions à revoir",
    review_initiative:      "Initiative oubliée",
  };

  function fmtDeadline(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    const diff = d - new Date();
    const abs = Math.abs(diff);
    if (abs < 3600000)    return Math.round(diff/60000)   + " min";
    if (abs < 86400000)   return Math.round(diff/3600000) + " h";
    if (abs < 86400000*30) return Math.round(diff/86400000) + " j";
    return d.toLocaleDateString("fr");
  }

  /* ───────── Loaders ───────── */
  let _globexEnabled = false;

  async function _loadGlobexEnabled() {
    try {
      const en = await J.api.get("/api/workspace/globex/enabled");
      _globexEnabled = !!(en && en.enabled);
    } catch (_) { _globexEnabled = false; }
    return _globexEnabled;
  }

  async function _loadGlobexInitiatives() {
    if (!await _loadGlobexEnabled()) return [];
    try {
      return await J.api.get("/api/workspace/globex/initiatives") || [];
    } catch (_) { return []; }
  }

  async function _loadGlobexOverview() {
    if (!_globexEnabled) return null;
    try { return await J.api.get("/api/workspace/globex/overview"); }
    catch (_) { return null; }
  }

  async function _loadGlobexMissions() {
    if (!_globexEnabled) return [];
    try { return await J.api.get("/api/workspace/globex/missions") || []; }
    catch (_) { return []; }
  }

  function _mapJarvisInitiative(i) {
    const pMap = { haute:"high", moyen:"med", basse:"low", high:"high", med:"med", low:"low" };
    return {
      id:       i.id,
      title:    i.title,
      type:     i.type || "Action",
      priority: pMap[String(i.priority||"").toLowerCase()] || "low",
      source:   "Jarvis",
      due:      i.created_at ? J.fmt.relTime(i.created_at) : "—",
      autonomy_level:      i.autonomy_level,
      permission_required: i.permission_required,
      cost_max_usd:        i.cost_max_usd,
      risk:                i.risk,
      deadline:            i.deadline,
      next_action:         i.next_action,
      requires_validation: i.requires_validation,
      origin: "jarvis",
      raw:      i,
    };
  }

  function _mapGlobexInitiative(g) {
    const pMap = { high:"high", med:"med", low:"low" };
    const isInfo = g.execution_mode === "info" || g.type === "sla_alert" || g.type === "dormant_account";
    return {
      id:       g.id,
      title:    g.title,
      type:     (g.tool || g.type || "Globex").toUpperCase(),
      priority: pMap[String(g.priority||"").toLowerCase()] || "med",
      source:   "GLOBEX",
      due:      g.created_at ? J.fmt.relTime(g.created_at) : "—",
      autonomy_level: isInfo ? null : 5,
      requires_validation: !isInfo,
      approval_id: g.approval_id,
      draft_content: g.draft_content || "",
      reasoning: g.reasoning || g.context || "",
      tool: g.tool || g.action,
      origin: "globex",
      raw: g,
    };
  }

  function _initSortWeight(i) {
    let w = 0;
    if (i.origin === "globex" && i.approval_id) w += 200;
    if (i.priority === "high") w += 40;
    if (i.priority === "med") w += 20;
    if (i.origin === "globex") w += 10;
    return w;
  }

  function openGlobexInChat(i) {
    if (!i || !i.approval_id) return;
    try {
      sessionStorage.setItem("jarvis_globex_pending", JSON.stringify({
        approval_id: i.approval_id,
        hint: i.reasoning || i.title || "",
      }));
    } catch (_) {}
    window.location.href = "/";
  }

  function buildGlobexInitPanel(panel, i) {
    const raw = i.raw || {};
    const hdr = el("div", { class: "panel-hdr" });
    hdr.appendChild(el("button", { class: "panel-close", text: "×" }));
    hdr.querySelector(".panel-close").addEventListener("click", closePanel);
    hdr.appendChild(el("div", { class: "panel-title", text: i.title || "Action Globex" }));
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });
    const meta = el("div", { class: "panel-section" });
    meta.appendChild(el("div", { class: "panel-section-title", text: "Détails" }));
    meta.appendChild(el("p", { text: "Outil : " + (i.tool || raw.action || "—") }));
    if (raw.mission_id) meta.appendChild(el("p", { text: "Mission #" + raw.mission_id }));
    if (i.reasoning) {
      const r = el("pre", { class: "panel-pre" });
      r.textContent = i.reasoning;
      meta.appendChild(r);
    }
    body.appendChild(meta);

    if (i.draft_content) {
      const draft = el("div", { class: "panel-section" });
      draft.appendChild(el("div", { class: "panel-section-title", text: "Paramètres" }));
      const pre = el("pre", { class: "panel-pre" });
      pre.textContent = i.draft_content;
      draft.appendChild(pre);
      body.appendChild(draft);
    }

    const actSec = el("div", { class: "panel-section", style: { display: "flex", gap: "8px", flexWrap: "wrap" } });
    if (i.approval_id) {
      const approveBtn = el("button", { class: "m-btn", text: "Valider" });
      approveBtn.addEventListener("click", async () => {
        approveBtn.disabled = true;
        await approveGlobexInit(i.approval_id, approveBtn);
        closePanel();
      });
      const rejectBtn = el("button", { class: "m-btn danger", text: "Refuser" });
      rejectBtn.addEventListener("click", async () => {
        rejectBtn.disabled = true;
        await rejectGlobexInit(i.approval_id, rejectBtn);
        closePanel();
      });
      const chatBtn = el("button", { class: "m-btn m-btn--ghost", text: "Ouvrir dans le chat" });
      chatBtn.addEventListener("click", () => openGlobexInChat(i));
      actSec.appendChild(approveBtn);
      actSec.appendChild(rejectBtn);
      actSec.appendChild(chatBtn);
    }
    body.appendChild(actSec);
    panel.appendChild(body);
  }

  function _renderGlobexKpiStrip(signals) {
    if (!signals) return null;
    const grid = el("div", { class: "kpi-strip kpi-strip--globex" });
    const items = [
      { lbl: "Colis suivis", val: signals.tracking_total || 0 },
      { lbl: "Retards", val: signals.tracking_delayed || 0 },
      { lbl: "Tickets ouverts", val: signals.open_tickets || 0 },
      { lbl: "Validations", val: signals.pending_approvals || 0 },
      { lbl: "SLA dépassés", val: signals.sla_breaches || 0 },
      { lbl: "Comptes dormants", val: signals.dormant_accounts || 0 },
    ];
    items.forEach(k => {
      const card = el("div", { class: "kpi-card" });
      card.appendChild(el("div", { class: "kpi-lbl", text: k.lbl }));
      card.appendChild(el("div", { class: "kpi-val", text: J.fmt.num(k.val) }));
      grid.appendChild(card);
    });
    return grid;
  }

  async function _loadGlobexAnalytics() {
    if (!await _loadGlobexEnabled()) return null;
    try { return await J.api.get("/api/workspace/globex/analytics"); }
    catch (_) { return null; }
  }

  async function loadInitiatives() {
    const [jarvisRaw, globexRaw] = await Promise.all([
      J.api.get("/api/initiatives").catch(() => []),
      _loadGlobexInitiatives(),
    ]);
    const merged = (jarvisRaw || []).map(_mapJarvisInitiative)
      .concat((globexRaw || []).map(_mapGlobexInitiative));
    merged.sort((a, b) => {
      const dw = _initSortWeight(b) - _initSortWeight(a);
      if (dw !== 0) return dw;
      const ta = (a.raw && a.raw.created_at) || "";
      const tb = (b.raw && b.raw.created_at) || "";
      return tb.localeCompare(ta);
    });
    return merged;
  }

  async function loadMissions() {
    const sMap = { running:"run", planning:"run", waiting:"wait", queued:"queue", queue:"queue", done:"done", failed:"failed", killed:"killed", completed:"done", pending:"run" };
    const toJarvisRow = p => ({
      id:     p.id ? p.id.slice(0,6).toUpperCase() : "?",
      status: sMap[p.status] || "run",
      title:  p.title || p.instruction || "Mission sans titre",
      sub:    "jarvis · " + (p.status||"running"),
      prog:   p.steps_total > 0 ? p.steps_done/p.steps_total : (p.status === "done" ? 1 : 0),
      cur:    p.steps_done||null,
      tot:    p.steps_total||null,
      rawId:  p.id,
      origin: "jarvis",
    });
    const toGlobexRow = m => ({
      id:     "GLB" + String(m.id || "?").slice(0,4),
      status: sMap[m.status] || "run",
      title:  m.title || "Mission Globex",
      sub:    "globex · " + (m.agent_type || m.schedule_type || "agent")
        + (m.scheduled_at ? " · planifié" : ""),
      prog:   m.progress != null ? m.progress : (m.steps_total > 0 ? m.steps_done/m.steps_total : 0),
      cur:    m.steps_done||null,
      tot:    m.steps_total||null,
      rawId:  null,
      origin: "globex",
      raw:    m,
    });
    const [jarvisRaw, globexRaw] = await Promise.all([
      J.api.get("/api/projects").catch(() => []),
      _loadGlobexMissions(),
    ]);
    const active = (jarvisRaw || []).filter(p => p.status !== "done" && p.status !== "failed" && p.status !== "killed").map(toJarvisRow)
      .concat((globexRaw || []).filter(m => m.status !== "completed" && m.status !== "failed" && m.status !== "done").map(toGlobexRow));
    const ended = (jarvisRaw || []).filter(p => p.status === "done" || p.status === "failed" || p.status === "killed").map(toJarvisRow)
      .concat((globexRaw || []).filter(m => m.status === "completed" || m.status === "failed" || m.status === "done").map(toGlobexRow));
    active.sort((a, b) => (b.raw && b.raw.updated_at || "").localeCompare(a.raw && a.raw.updated_at || ""));
    ended.sort((a, b) => (b.raw && b.raw.updated_at || "").localeCompare(a.raw && a.raw.updated_at || ""));
    return { active, ended };
  }

  /* ───────── Page builder ───────── */
  function pageWrapper(pageId, title, meta, body) {
    const idx = PAGES.findIndex(p => p.id === pageId);
    const num = String(idx + 1).padStart(2, "0");
    const wrap = el("div", { class: "page room-in" });

    const head = el("div", { class: "page-head" });
    const left = el("div");
    const eyebrow = el("div", { class: "page-eyebrow" });
    eyebrow.appendChild(el("span", { class: "num", text: num }));
    eyebrow.appendChild(el("span", { text: " · " + PAGES[idx].label.toUpperCase() }));
    left.appendChild(eyebrow);
    left.appendChild(el("h1", { text: title }));
    head.appendChild(left);
    if (meta) {
      const m = el("div", { class: "page-head-meta" });
      m.innerHTML = meta;
      head.appendChild(m);
    }
    wrap.appendChild(head);

    const pb = el("div", { class: "page-body" });
    pb.appendChild(body);
    wrap.appendChild(pb);
    return wrap;
  }

  function ghostSec(title, sub, right, content) {
    const sec = el("div", { class: "ghost-sec" });
    const hd = el("div", { class: "ghost-sec-hd" });
    const l = el("div");
    l.appendChild(el("div", { class: "ghost-sec-title", text: title }));
    if (sub) l.appendChild(el("div", { class: "ghost-sec-sub", text: sub }));
    hd.appendChild(l);
    if (right) {
      const r = el("div", { class: "ghost-sec-r" });
      /* Accepte un Node (badge DOM) OU une string (texte simple).
         Avant : text: right forçait textContent → le HTML s'affichait littéral. */
      if (right instanceof Node) r.appendChild(right);
      else r.textContent = String(right);
      hd.appendChild(r);
    }
    sec.appendChild(hd);
    sec.appendChild(content);
    return sec;
  }

  /* ───────── Aperçu ───────── */
  async function renderApercu() {
    const [inits, { active }, tasksRaw, globexOverview] = await Promise.all([
      loadInitiatives(),
      loadMissions(),
      J.api.get("/api/tasks").catch(() => []),
      _loadGlobexOverview(),
    ]);
    const shown = inits.slice(0, 5);
    const highCount = inits.filter(i => i.priority === "high").length;
    const tasks = (tasksRaw.tasks || tasksRaw || [])
      .map(t => ({ id: t.id, label: t.title || t.label || t.text || "", done: !!(t.done || t.checked), src: t.source || "NOTION" }))
      .filter(t => t.label);

    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "44px" } });

    if (globexOverview && globexOverview.signals) {
      const kpi = _renderGlobexKpiStrip(globexOverview.signals);
      if (kpi) wrap.appendChild(kpi);
    }

    // Briefing Globex FedEx
    if (globexOverview && globexOverview.briefing_lines && globexOverview.briefing_lines.length) {
      const briefList = el("div");
      globexOverview.briefing_lines.forEach(line => {
        const row = el("div", { class: "row-stripe" });
        const inner = el("div", { class: "row-stripe-inner" });
        inner.appendChild(el("div", { class: "row-stripe-title", text: line }));
        row.appendChild(inner);
        briefList.appendChild(row);
      });
      const sig = globexOverview.signals || {};
      const sub = sig.pending_approvals
        ? sig.pending_approvals + " validation(s) · " + (sig.open_tickets || 0) + " tickets"
        : "Plateforme FedEx";
      wrap.appendChild(ghostSec(
        "Briefing Globex",
        sub,
        el("span", { class: "badge badge--solid", text: "GLOBEX" }),
        briefList
      ));
    }

    // À traiter — toujours affiché
    {
      const list = el("div");
      if (shown.length) {
        shown.forEach(i => list.appendChild(renderInitRow(i)));
      } else {
        list.appendChild(el("div", { class: "j-empty", text: "Aucune initiative en attente" }));
      }
      const sub = shown.length
        ? shown.length + " en attente" + (highCount ? " · " + highCount + " urgente" + (highCount > 1 ? "s" : "") : "")
        : "—";
      wrap.appendChild(ghostSec("À traiter", sub, shown.length ? "voir tout →" : null, list));
    }

    // Missions — toujours affiché
    const missionList = el("div");
    if (active.length) {
      active.slice(0, 3).forEach(m => missionList.appendChild(renderMissionRow(m)));
    } else {
      missionList.appendChild(el("div", { class: "j-empty", text: "Aucune mission en cours" }));
    }
    wrap.appendChild(ghostSec(
      "Missions",
      active.length ? active.length + " en cours" : "—",
      null,
      missionList
    ));

    // Tâches
    const taskList = el("div");
    if (tasks.length) {
      tasks.forEach(t => taskList.appendChild(buildTaskRow(t, taskList)));
    } else {
      taskList.appendChild(el("div", { class: "j-empty", text: "Aucune tâche" }));
    }
    wrap.appendChild(ghostSec(
      "Tâches",
      tasks.length ? tasks.filter(t => t.done).length + " / " + tasks.length + " terminées" : "—",
      null,
      taskList
    ));

    const page = pageWrapper(
      "apercu",
      "Ce qui mérite ton attention",
      null,
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Initiatives + Skills à valider + Maintenance Curator ─────────
     Inbox unifiée d'arbitrage : un seul écran pour tout ce qui demande
     ma décision (initiatives proactives, candidates Skill Lab, patches
     Curator). Trois sections distinctes, ordonnées par urgence visuelle. */
  async function renderInitiatives() {
    const [inits, skills, curatorReport] = await Promise.all([
      loadInitiatives(),
      _loadSkillsPending(),
      _loadCuratorReport(),
    ]);

    /* ── Section 1 — Initiatives ── */
    const list = el("div");
    if (!inits.length) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucune initiative en attente" }));
    } else {
      inits.forEach(i => list.appendChild(renderInitRow(i, true)));
    }

    const wrap = el("div");
    wrap.appendChild(ghostSec(
      "En attente",
      inits.length + " initiatives · Jarvis + Globex",
      null,
      list
    ));

    /* ── Section 2 — Skills à valider (Skill Lab PHASE 4) ── */
    if (skills.length) {
      const skillsList = el("div");
      skills.forEach(c => skillsList.appendChild(_renderSkillRow(c)));
      wrap.appendChild(ghostSec(
        "Skills à valider",
        skills.length + " candidate" + (skills.length>1?"s":"") + " · sandbox vert, attend ta décision",
        el("span", { class: "badge badge--skills", text: "SKILLS" }),
        skillsList
      ));
    }

    /* ── Section 3 — Maintenance (Curator PHASE 6) ── */
    if (curatorReport && curatorReport.patches && curatorReport.patches.length) {
      const patches = curatorReport.patches;
      const patchList = el("div");
      patches.forEach((p, idx) => patchList.appendChild(_renderPatchRow(p, idx, renderInitiatives)));
      const scanDate = curatorReport.generated_at
        ? new Date(curatorReport.generated_at).toLocaleString("fr") : "—";
      wrap.appendChild(ghostSec(
        "Maintenance",
        patches.length + " suggestion" + (patches.length>1?"s":"") + " · scan " + scanDate,
        el("span", { class: "badge badge--maintenance", text: "MAINTENANCE" }),
        patchList
      ));
    }

    const page = pageWrapper(
      "initiatives",
      "Ce qui mérite ton arbitrage",
      '<span class="v">' + inits.length + '</span> à traiter'
        + (skills.length ? ' · <span class="v">' + skills.length + '</span> skill' + (skills.length>1?'s':'') : '')
        + (curatorReport && curatorReport.patches && curatorReport.patches.length
            ? ' · <span class="v">' + curatorReport.patches.length + '</span> patch'
              + (curatorReport.patches.length>1?'s':'') : ''),
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Skills à valider (Skill Lab) ───────── */

  async function _loadSkillsPending() {
    try {
      return await J.api.get("/api/skills/lab/candidates?status=sandboxed_pass") || [];
    } catch (_) { return []; }
  }

  function _renderSkillRow(c) {
    const row = el("div", { class: "row-stripe skill-row" });
    const bar = el("div", { class: "row-stripe-bar med" });
    row.appendChild(bar);

    const inner = el("div", { class: "row-stripe-inner" });
    inner.appendChild(el("div", { class: "row-stripe-title", text: c.name }));
    const meta = el("div", { class: "row-stripe-meta" });
    meta.appendChild(el("span", { class: "badge badge--solid", text: "SKILL" }));
    if (c.sandbox_notes) {
      meta.appendChild(el("span", { text: (c.sandbox_notes || "").slice(0, 80) }));
    }
    inner.appendChild(meta);
    row.appendChild(inner);

    const right = el("div", { class: "row-stripe-right" });
    const promote = el("button", { class: "m-btn", text: "✓ Promouvoir" });
    promote.addEventListener("click", async (e) => {
      e.stopPropagation();
      promote.disabled = true; promote.textContent = "…";
      try {
        await J.api.post("/api/skills/lab/" + encodeURIComponent(c.name) + "/promote");
        J.notify({ kind: "success", text: c.name + " promue" });
        renderInitiatives();
      } catch (err) {
        J.notify({ kind: "error", text: err.message });
        promote.disabled = false; promote.textContent = "✓ Promouvoir";
      }
    });
    const reject = el("button", { class: "m-btn danger", text: "✗ Rejeter" });
    reject.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Rejeter définitivement « " + c.name + " » ?")) return;
      reject.disabled = true; reject.textContent = "…";
      try {
        await J.api.post("/api/skills/lab/" + encodeURIComponent(c.name) + "/reject");
        J.notify({ kind: "info", text: c.name + " rejetée" });
        renderInitiatives();
      } catch (err) {
        J.notify({ kind: "error", text: err.message });
        reject.disabled = false; reject.textContent = "✗ Rejeter";
      }
    });
    right.appendChild(promote); right.appendChild(reject);
    row.appendChild(right);
    return row;
  }

  /* ───────── Maintenance (Curator patches) ─────────
     Routage par type vers les endpoints PROPRES — apply_patch (403) n'est
     JAMAIS appelé. Pas d'ack persistant : le rapport se régénère sur l'état
     réel à chaque scan, les patches obsolètes disparaîtront d'eux-mêmes. */

  async function _loadCuratorReport() {
    try { return await J.api.get("/api/curator/latest"); }
    catch (_) { return null; }
  }

  function _renderPatchRow(patch, idx, reload) {
    const row = el("div", { class: "row-stripe patch-row" });
    const bar = el("div", { class: "row-stripe-bar low" });
    row.appendChild(bar);

    const inner = el("div", { class: "row-stripe-inner" });
    inner.appendChild(el("div", { class: "row-stripe-title", text: patch.description }));
    const meta = el("div", { class: "row-stripe-meta" });
    meta.appendChild(el("span", { class: "badge badge--solid", text: PATCH_LABELS[patch.kind] || patch.kind }));
    meta.appendChild(el("span", { text: "cible : " + patch.target }));
    if (patch.reason) {
      meta.appendChild(el("span", { style: { opacity: ".4" }, text: "·" }));
      meta.appendChild(el("span", { text: patch.reason }));
    }
    inner.appendChild(meta);
    row.appendChild(inner);

    const right = el("div", { class: "row-stripe-right" });
    _appendPatchActions(right, patch, idx, reload);
    row.appendChild(right);
    return row;
  }

  function _appendPatchActions(container, patch, idx, reload) {
    switch (patch.kind) {
      case "archive_fact": {
        const btn = el("button", { class: "m-btn", text: "✓ Archiver ce fact" });
        btn.addEventListener("click", async () => {
          if (!confirm("Archiver le fact " + patch.target + " ?\nTrace un event human_correction en audit.")) return;
          btn.disabled = true; btn.textContent = "…";
          try {
            await J.api.post("/api/memory/correct", {
              target_fact_id: patch.target,
              new_status: "archived",
              correction_text: "Archivé via patch Curator #" + idx,
            });
            J.notify({ kind: "success", text: "Fact archivé — event tracé en audit" });
            if (reload) reload();
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            btn.disabled = false; btn.textContent = "✓ Archiver ce fact";
          }
        });
        container.appendChild(btn);
        break;
      }
      case "reject_stale_candidate": {
        const btn = el("button", { class: "m-btn danger", text: "✗ Rejeter cette candidate" });
        btn.addEventListener("click", async () => {
          if (!confirm("Rejeter la candidate " + patch.target + " ?")) return;
          btn.disabled = true; btn.textContent = "…";
          try {
            await J.api.post("/api/skills/lab/" + encodeURIComponent(patch.target) + "/reject");
            J.notify({ kind: "info", text: patch.target + " rejetée" });
            if (reload) reload();
          } catch (e) {
            J.notify({ kind: "error", text: e.message });
            btn.disabled = false; btn.textContent = "✗ Rejeter cette candidate";
          }
        });
        container.appendChild(btn);
        break;
      }
      case "review_initiative": {
        const btn = el("button", { class: "m-btn", text: "↑ Voir l'initiative" });
        btn.addEventListener("click", () => {
          /* Scroll vers la section "En attente" qui contient l'initiative. */
          const tgt = document.querySelector(".ghost-sec");
          if (tgt) tgt.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        container.appendChild(btn);
        break;
      }
      case "mark_skill_stale":
      case "archive_skill":
      case "review_contradiction":
      default: {
        const txt = el("span", {
          text: "Consultatif — pas d'action atomique",
          style: { fontSize: "11px", color: "var(--fg-3)", fontStyle: "italic" },
        });
        container.appendChild(txt);
        break;
      }
    }
  }

  /* PHASE 6 §10.1 — bloc gouvernance pour le panel détail.
     Renvoie null si aucune info §10.1 sur l'initiative (legacy). */
  function _buildGovBlock(raw) {
    const hasAny = (raw.autonomy_level != null) || (raw.cost_max_usd != null)
      || raw.risk || raw.deadline || raw.next_action || raw.requires_validation;
    if (!hasAny) return null;
    const sec = el("div", { class: "panel-section gov-panel" });
    sec.appendChild(el("div", { class: "panel-section-title", text: "Gouvernance §10.1" }));
    const chips = el("div", { class: "gov-chips" });
    const chip = (text, extraClass) => {
      const c = el("span", { class: "gov-chip" + (extraClass ? " " + extraClass : ""), text });
      chips.appendChild(c);
    };
    if (raw.autonomy_level != null) {
      chip(raw.autonomy_level + " · " + (AUTONOMY_LABELS[raw.autonomy_level] || "—"));
    }
    if (raw.permission_required)  chip(raw.permission_required);
    if (raw.cost_max_usd != null) chip("≤ " + Number(raw.cost_max_usd).toFixed(2) + "$");
    if (raw.risk)                 chip(raw.risk, "risk-" + raw.risk);
    if (raw.deadline)             chip("deadline " + fmtDeadline(raw.deadline));
    sec.appendChild(chips);
    if (raw.next_action) {
      const next = el("div", { class: "gov-next" });
      next.appendChild(el("span", { class: "gov-next-lbl", text: "prochaine étape" }));
      next.appendChild(document.createTextNode(" " + raw.next_action));
      sec.appendChild(next);
    }
    return sec;
  }

  function buildInitPanel(panel, i) {
    const raw = i.raw || {};
    const closeBtn = el("button", { class: "panel-close", text: "✕" });
    closeBtn.addEventListener("click", closePanel);

    const hdr = el("div", { class: "mp-header" });
    const left = el("div", { class: "mp-header-left" });
    const badge = el("div", { class: "mp-status-badge run", text: (raw.type || i.type || "").toUpperCase().replace("_", " ") });
    const info = el("div");
    info.appendChild(el("div", { class: "mp-title", text: i.title }));
    info.appendChild(el("div", { class: "mp-sub", text: i.source || "Jarvis proactif · " + (i.due || "") }));
    left.appendChild(badge); left.appendChild(info);
    hdr.appendChild(left); hdr.appendChild(closeBtn);
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });

    const addSec = (title, text) => {
      if (!text) return;
      const s = el("div", { class: "panel-section" });
      s.appendChild(el("div", { class: "panel-section-title", text: title }));
      s.appendChild(el("div", { style: { fontSize: "12px", lineHeight: "1.6", color: "var(--fg-2)" }, text: text }));
      body.appendChild(s);
    };

    /* PHASE 6 §10.1 — bloc gouvernance (tout en haut pour qu'il soit visible
       avant les actions). N'affiche rien si l'initiative est legacy pré-PHASE 6. */
    const govEl = _buildGovBlock(raw);
    if (govEl) body.appendChild(govEl);

    addSec("Action proposée", raw.action || i.title);
    addSec("Contexte", raw.context);
    addSec("Raisonnement", raw.reasoning);

    if (raw.draft_content) {
      const s = el("div", { class: "panel-section" });
      s.appendChild(el("div", { class: "panel-section-title", text: "Brouillon" }));
      const pre = el("div", {
        style: { fontFamily: "var(--mono)", fontSize: "11px", lineHeight: "1.6",
                 whiteSpace: "pre-wrap", wordBreak: "break-word",
                 background: "rgba(74,158,255,0.04)", border: "1px solid rgba(74,158,255,0.10)",
                 borderRadius: "6px", padding: "10px 12px", color: "var(--fg-2)" },
        text: raw.draft_content,
      });
      s.appendChild(pre);
      body.appendChild(s);
    }

    // Actions
    const actSec = el("div", { class: "panel-section", style: { display: "flex", gap: "8px", marginTop: "8px" } });
    const approveBtn = el("button", { class: "m-btn", text: raw.type === "draft_response" ? "📤 Préparer & envoyer" : "✓ Approuver" });
    approveBtn.addEventListener("click", async () => {
      approveBtn.textContent = "…"; approveBtn.disabled = true;
      try {
        await J.api.post("/api/initiatives/" + raw.id + "/approve");
        J.notify({ kind: "success", text: "Initiative approuvée" });
        closePanel();
        if (_activePage === "apercu") renderApercu(); else renderInitiatives();
      } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); approveBtn.disabled = false; approveBtn.textContent = "Approuver"; }
    });
    const rejectBtn = el("button", { class: "m-btn danger", text: "✗ Rejeter" });
    rejectBtn.addEventListener("click", async () => {
      rejectBtn.textContent = "…"; rejectBtn.disabled = true;
      try {
        await J.api.post("/api/initiatives/" + raw.id + "/reject");
        J.notify({ kind: "success", text: "Initiative rejetée" });
        closePanel();
        if (_activePage === "apercu") renderApercu(); else renderInitiatives();
      } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); rejectBtn.disabled = false; rejectBtn.textContent = "Rejeter"; }
    });
    actSec.appendChild(approveBtn);
    actSec.appendChild(rejectBtn);
    body.appendChild(actSec);

    panel.appendChild(body);
  }

  function renderInitRow(i, showActions) {
    const row = el("div", { class: "row-stripe", style: { cursor: "pointer" } });
    row.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      if (i.origin === "globex") {
        openPanel(buildGlobexInitPanel, i);
        return;
      }
      openPanel(buildInitPanel, i);
    });

    // Priority bar
    const bar = el("div", { class: "row-stripe-bar " + (i.priority || "low") });
    row.appendChild(bar);

    // Content
    const inner = el("div", { class: "row-stripe-inner" });
    const titleRow = el("div", { class: "row-stripe-title-row" });
    titleRow.appendChild(el("div", { class: "row-stripe-title", text: i.title }));
    /* PHASE 6 §10.1 — niveau 5 force validation par principe (cf. needs_human_validation) */
    if (i.autonomy_level === 5) {
      titleRow.appendChild(el("span", {
        class: "lvl5-badge",
        text: "🚨 NIVEAU 5 — VALIDATION FORCÉE",
        title: "EXTERNAL_ACTION — validation humaine obligatoire (CDC §10)",
      }));
    }
    inner.appendChild(titleRow);
    const meta = el("div", { class: "row-stripe-meta" });
    meta.appendChild(el("span", { class: "badge badge--solid", text: i.type || "Action" }));
    if (i.origin === "globex") {
      meta.appendChild(el("span", { class: "badge badge--globex", text: "GLOBEX" }));
      if (i.raw && i.raw.execution_mode === "info") {
        if (i.raw.type === "dormant_account") {
          meta.appendChild(el("span", { class: "badge badge--sla", text: "INACTIF" }));
        } else {
          meta.appendChild(el("span", { class: "badge badge--sla", text: "SLA" }));
        }
      }
    }
    meta.appendChild(el("span", { text: i.source || "Jarvis" }));
    meta.appendChild(el("span", { style: { opacity: ".4" }, text: "·" }));
    meta.appendChild(el("span", { text: i.due || "—" }));
    inner.appendChild(meta);
    row.appendChild(inner);

    // Right — actions or ID
    const right = el("div", { class: "row-stripe-right" });
    if (showActions && i.origin === "globex" && i.approval_id) {
      const approve = el("button", { class: "m-btn", text: "Valider" });
      approve.addEventListener("click", (e) => { e.stopPropagation(); approveGlobexInit(i.approval_id, approve); });
      const reject = el("button", { class: "m-btn danger", text: "Refuser" });
      reject.addEventListener("click", (e) => { e.stopPropagation(); rejectGlobexInit(i.approval_id, reject); });
      const chat = el("button", { class: "m-btn m-btn--ghost", text: "Chat" });
      chat.title = "Ouvrir dans le chat Jarvis";
      chat.addEventListener("click", (e) => { e.stopPropagation(); openGlobexInChat(i); });
      right.appendChild(approve); right.appendChild(reject); right.appendChild(chat);
    } else if (showActions && i.raw && i.origin !== "globex") {
      const approve = el("button", { class: "m-btn", text: "Approuver" });
      approve.addEventListener("click", (e) => { e.stopPropagation(); approveInit(i.raw.id, approve); });
      const reject = el("button", { class: "m-btn danger", text: "Rejeter" });
      reject.addEventListener("click", (e) => { e.stopPropagation(); rejectInit(i.raw.id, reject); });
      right.appendChild(approve); right.appendChild(reject);
    } else {
      right.appendChild(el("span", { style: { fontFamily: "var(--mono)", fontSize: "10px", color: "var(--fg-3)" }, text: i.id || "" }));
    }
    row.appendChild(right);
    return row;
  }

  async function approveGlobexInit(approvalId, btn) {
    btn.textContent = "…"; btn.disabled = true;
    try {
      const res = await J.api.post("/api/workspace/globex/approve/" + approvalId);
      J.notify({ kind: "success", text: res.reply || "Action Globex validée" });
      if (_activePage === "apercu") renderApercu(); else renderInitiatives();
    } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); btn.textContent = "Valider"; btn.disabled = false; }
  }
  async function rejectGlobexInit(approvalId, btn) {
    btn.textContent = "…"; btn.disabled = true;
    try {
      await J.api.post("/api/workspace/globex/reject/" + approvalId);
      J.notify({ kind: "info", text: "Action Globex refusée" });
      if (_activePage === "apercu") renderApercu(); else renderInitiatives();
    } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); btn.textContent = "Refuser"; btn.disabled = false; }
  }

  async function approveInit(id, btn) {
    btn.textContent = "…"; btn.disabled = true;
    try {
      await J.api.post("/api/initiatives/" + id + "/approve");
      J.notify({ kind: "success", text: "Initiative approuvée" });
      renderInitiatives();
    } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); btn.textContent = "Approuver"; btn.disabled = false; }
  }
  async function rejectInit(id, btn) {
    btn.textContent = "…"; btn.disabled = true;
    try {
      await J.api.post("/api/initiatives/" + id + "/reject");
      J.notify({ kind: "success", text: "Initiative rejetée" });
      renderInitiatives();
    } catch (e) { J.notify({ kind: "error", text: "Erreur : " + e.message }); btn.textContent = "Rejeter"; btn.disabled = false; }
  }

  /* ───────── Panel (mission detail) ───────── */
  let _panelKeyListener = null;

  function initPanel() {
    if (document.getElementById("dash-detail-panel")) return;
    const overlay = el("div", { id: "dash-detail-overlay" });
    overlay.addEventListener("click", closePanel);
    document.body.appendChild(overlay);
    document.body.appendChild(el("div", { id: "dash-detail-panel" }));
    _panelKeyListener = e => { if (e.key === "Escape") closePanel(); };
    document.addEventListener("keydown", _panelKeyListener);
  }

  function closePanel() {
    const p = document.getElementById("dash-detail-panel");
    const o = document.getElementById("dash-detail-overlay");
    if (p) p.classList.remove("open");
    if (o) o.classList.remove("open");
  }

  function openPanel(buildFn, data) {
    initPanel();
    const panel = document.getElementById("dash-detail-panel");
    panel.innerHTML = "";
    buildFn(panel, data);
    requestAnimationFrame(() => {
      document.getElementById("dash-detail-overlay").classList.add("open");
      panel.classList.add("open");
    });
  }

  /* ───────── Simple markdown renderer ───────── */
  function renderMd(md) {
    if (!md) return "";
    let html = md
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      // fenced code blocks
      .replace(/```[\w]*\n?([\s\S]*?)```/g, (_, c) => "<pre><code>" + c.trim() + "</code></pre>")
      // headings
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>")
      // bold / italic
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      // inline code
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      // links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      // bullet lists (simple)
      .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
      // paragraphs: double newlines
      .split(/\n{2,}/).map(block => {
        if (/^<(h[1-3]|pre|li|ul|ol)/.test(block.trim())) return block;
        if (block.includes("<li>")) return "<ul>" + block + "</ul>";
        return "<p>" + block.replace(/\n/g, "<br>") + "</p>";
      }).join("\n");
    return html;
  }

  /* ───────── File viewer popup ───────── */
  function openFileViewer(projectId, filePath) {
    let popup = document.getElementById("dash-file-popup");
    if (!popup) {
      const ov = el("div", { id: "dash-file-popup-overlay" });
      ov.addEventListener("click", () => closeFileViewer());
      document.body.appendChild(ov);
      popup = el("div", { id: "dash-file-popup" });
      document.body.appendChild(popup);
    }
    popup.innerHTML = '<div class="fp-loading">Chargement…</div>';
    document.getElementById("dash-file-popup-overlay").classList.add("open");
    popup.classList.add("open");

    J.api.get("/api/projects/" + projectId + "/files/" + filePath)
      .then(res => {
        const content = res.content || "";
        const isMd = filePath.endsWith(".md") || filePath.endsWith(".markdown");
        const isTxt = /\.(txt|json|yaml|yml|toml|ini|csv|py|js|ts|sh|env)$/.test(filePath);

        popup.innerHTML = "";
        const hdr = el("div", { class: "fp-header" });
        hdr.appendChild(el("span", { class: "fp-path", text: filePath }));
        const closeBtn = el("button", { class: "fp-close", text: "✕" });
        closeBtn.addEventListener("click", closeFileViewer);
        hdr.appendChild(closeBtn);
        popup.appendChild(hdr);

        const body = el("div", { class: "fp-body" });
        if (isMd) {
          const rendered = el("div", { class: "fp-markdown" });
          rendered.innerHTML = renderMd(content);
          body.appendChild(rendered);
        } else {
          const pre = el("pre", { class: "fp-code" });
          pre.textContent = content;
          body.appendChild(pre);
        }
        popup.appendChild(body);
      })
      .catch(e => {
        popup.innerHTML = '<div class="fp-loading" style="color:var(--red)">Erreur : ' + e.message + '</div>';
      });
  }

  function closeFileViewer() {
    const ov = document.getElementById("dash-file-popup-overlay");
    const popup = document.getElementById("dash-file-popup");
    if (ov) ov.classList.remove("open");
    if (popup) popup.classList.remove("open");
  }

  /* ───────── Mission detail panel ───────── */
  async function buildMissionPanel(panel, m) {
    // Header
    const hdr = el("div", { class: "mp-header" });
    const left = el("div", { class: "mp-header-left" });
    const badge = el("div", { class: "mp-status-badge " + m.status, text: m.status.toUpperCase() });
    const info = el("div");
    info.appendChild(el("div", { class: "mp-title", text: m.title }));
    info.appendChild(el("div", { class: "mp-sub", text: m.id + " · " + m.sub }));
    left.appendChild(badge); left.appendChild(info);
    const closeBtn = el("button", { class: "panel-close", text: "✕" });
    closeBtn.addEventListener("click", closePanel);
    hdr.appendChild(left); hdr.appendChild(closeBtn);
    panel.appendChild(hdr);

    const body = el("div", { class: "panel-body" });

    // Progress bar
    const progSec = el("div", { class: "panel-section" });
    const progBar = el("div", { class: "mp-prog-bar" });
    progBar.appendChild(el("div", { style: { width: Math.round((m.prog||0)*100) + "%" } }));
    progSec.appendChild(progBar);
    progSec.appendChild(el("div", { class: "mp-prog-label", text: m.cur != null ? m.cur + " / " + (m.tot||"?") + " étapes" : "En cours…" }));
    body.appendChild(progSec);

    body.appendChild(el("div", { class: "mp-loading", text: "Chargement des détails…" }));
    panel.appendChild(body);

    // Fetch detailed data
    let detail = null, files = [];
    try { [detail, files] = await Promise.all([
      J.api.get("/api/projects/" + m.rawId),
      J.api.get("/api/projects/" + m.rawId + "/files"),
    ]); } catch (_) {}

    // Remove loading indicator
    const loadEl = body.querySelector(".mp-loading");
    if (loadEl) loadEl.remove();

    // Steps
    if (detail && detail.steps && detail.steps.length) {
      const stepSec = el("div", { class: "panel-section" });
      stepSec.appendChild(el("div", { class: "panel-section-title", text: "Étapes" }));
      detail.steps.forEach((s, i) => {
        const row = el("div", { class: "mp-step mp-step--" + (s.status || "pending") });
        const num = el("div", { class: "mp-step-num", text: String(i + 1).padStart(2, "0") });
        const content = el("div", { class: "mp-step-content" });
        content.appendChild(el("div", { class: "mp-step-title", text: s.title || s.id }));
        const statusBadge = el("span", { class: "mp-step-status mp-step-status--" + (s.status || "pending"), text: s.status || "pending" });
        content.appendChild(statusBadge);
        if (s.output) {
          const out = el("div", { class: "mp-step-output", text: s.output.slice(0, 300) + (s.output.length > 300 ? "…" : "") });
          content.appendChild(out);
        }
        if (s.error) {
          const err = el("div", { class: "mp-step-error", text: s.error.slice(0, 200) });
          content.appendChild(err);
        }
        row.appendChild(num); row.appendChild(content);
        stepSec.appendChild(row);
      });
      body.appendChild(stepSec);
    }

    // Files
    if (files && files.length) {
      const fileSec = el("div", { class: "panel-section" });
      fileSec.appendChild(el("div", { class: "panel-section-title", text: "Fichiers produits" }));
      files.forEach(f => {
        const row = el("div", { class: "mp-file-row" });
        const icon = el("span", { class: "mp-file-icon", text: f.endsWith(".md") ? "📄" : f.endsWith(".json") ? "📋" : f.endsWith(".py") || f.endsWith(".js") ? "📝" : "📁" });
        const name = el("button", { class: "mp-file-name", text: f });
        name.addEventListener("click", () => openFileViewer(m.rawId, f));
        row.appendChild(icon); row.appendChild(name);
        fileSec.appendChild(row);
      });
      body.appendChild(fileSec);
    } else if (detail) {
      const fileSec = el("div", { class: "panel-section" });
      fileSec.appendChild(el("div", { class: "panel-section-title", text: "Fichiers produits" }));
      fileSec.appendChild(el("div", { class: "j-empty", text: "Aucun fichier produit" }));
      body.appendChild(fileSec);
    }

    // Actions
    if (m.rawId) {
      const actSec = el("div", { class: "panel-section" });
      actSec.appendChild(el("div", { class: "panel-section-title", text: "Actions" }));
      const actRow = el("div", { class: "mp-act-row" });
      const retryBtn = el("button", { class: "m-btn", text: "Retry" });
      retryBtn.addEventListener("click", async () => {
        retryBtn.textContent = "…"; retryBtn.disabled = true;
        try {
          await J.api.post("/api/projects/" + m.rawId + "/retry");
          J.notify({ kind: "success", text: "Relancée" });
          closePanel();
          renderMissions();
        } catch (e) { J.notify({ kind: "error", text: e.message }); retryBtn.textContent = "Retry"; retryBtn.disabled = false; }
      });
      actRow.appendChild(retryBtn);
      actSec.appendChild(actRow);
      body.appendChild(actSec);
    }
  }

  /* ───────── Missions ───────── */
  async function renderMissions() {
    const { active, ended } = await loadMissions();
    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "44px" } });

    const activeList = el("div");
    if (!active.length) {
      activeList.appendChild(el("div", { class: "j-empty", text: "Aucune mission active" }));
    } else {
      active.forEach(m => activeList.appendChild(renderMissionRow(m)));
    }
    wrap.appendChild(ghostSec("En cours", active.length + " active" + (active.length > 1 ? "s" : ""), null, activeList));

    if (ended.length) {
      const endedList = el("div");
      ended.forEach(m => endedList.appendChild(renderMissionRow(m)));
      wrap.appendChild(ghostSec("Terminées", ended.length + " mission" + (ended.length > 1 ? "s" : ""), null, endedList));
    }

    const page = pageWrapper(
      "missions",
      "Les missions en vol",
      '<span class="v">' + active.length + '</span> actives · <span class="v">' + ended.length + '</span> terminées',
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  function renderMissionRow(m) {
    const isEnded = m.status === "done" || m.status === "failed" || m.status === "killed";
    let cls = "mission-row mission-row--clickable";
    if (isEnded) cls += " mission-row--ended";
    if (m.status === "failed") cls += " mission-row--failed";
    const row = el("div", { class: cls });
    row.addEventListener("click", () => {
      if (m.origin === "globex") return;
      openPanel(buildMissionPanel, m);
    });

    const idCol = el("div");
    idCol.appendChild(el("div", { class: "m-id t-mono", text: m.id }));
    idCol.appendChild(el("div", { class: "m-status " + m.status, text: m.status.toUpperCase() }));
    row.appendChild(idCol);

    const titleCol = el("div");
    const titleRow = el("div", { style: { display: "flex", alignItems: "center", gap: "8px" } });
    titleRow.appendChild(el("div", { class: "m-title", text: m.title }));
    if (m.origin === "globex") {
      titleRow.appendChild(el("span", { class: "badge badge--globex", text: "GLOBEX" }));
    }
    titleCol.appendChild(titleRow);
    titleCol.appendChild(el("div", { class: "m-sub",   text: m.sub }));
    row.appendChild(titleCol);

    const progCol = el("div");
    const bar = el("div", { class: "m-prog-bar" });
    bar.appendChild(el("div", { style: { width: Math.round((m.prog||0)*100)+"%" } }));
    progCol.appendChild(bar);
    const meta = el("div", { class: "m-prog-meta" });
    meta.appendChild(el("span", { text: m.cur != null ? m.cur + " / " + (m.tot||"?") + " étapes" : "En cours" }));
    progCol.appendChild(meta);
    row.appendChild(progCol);

    const actCol = el("div", { class: "m-actions" });
    actCol.appendChild(el("span", { class: "m-detail-hint", text: "Détails →" }));
    row.appendChild(actCol);
    return row;
  }

  /* ───────── Tâches — helper partagé ───────── */
  function buildTaskRow(t, list) {
    const row = el("div", { class: "task-row " + (t.done ? "done" : "") });
    const chk = el("div", { class: "task-check" });
    const txt = el("div", { style: { flex: "1", minWidth: "0" } });
    txt.appendChild(el("div", { class: "task-label", text: t.label }));
    txt.appendChild(el("div", { class: "task-src",   text: t.src }));

    const del = el("div", { class: "task-del", text: "×" });
    del.title = "Supprimer";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      row.style.opacity = "0.4";
      try {
        await J.api.delete("/api/tasks/" + t.id);
        row.remove();
        if (list && !list.querySelectorAll(".task-row").length) {
          const empty = el("div", { class: "j-empty", text: "Aucune tâche" });
          const addBar = list.querySelector(".add-bar");
          if (addBar) list.insertBefore(empty, addBar);
          else list.appendChild(empty);
        }
      } catch (_) { row.style.opacity = ""; }
    });

    chk.addEventListener("click", async (e) => {
      e.stopPropagation();
      const newDone = !t.done;
      t.done = newDone;
      row.classList.toggle("done", newDone);
      J.api.patch("/api/tasks/" + t.id, { done: newDone }).catch(() => {
        t.done = !newDone;
        row.classList.toggle("done", !newDone);
      });
    });

    row.appendChild(chk); row.appendChild(txt); row.appendChild(del);
    return row;
  }

  /* ───────── Tâches ───────── */
  async function renderTaches() {
    let tasks = [];
    try {
      const raw = await J.api.get("/api/tasks");
      tasks = (raw.tasks || raw || []).map(t => ({
        id: t.id,
        label: t.title || t.label || t.text || "",
        done: !!(t.done || t.checked),
        src: t.source || "NOTION",
      })).filter(t => t.label);
    } catch (_) {}

    const list = el("div");

    if (!tasks.length) {
      list.appendChild(el("div", { class: "j-empty", text: "Aucune tâche" }));
    } else {
      tasks.forEach(t => list.appendChild(buildTaskRow(t, list)));
    }

    const addBar = el("div", { class: "add-bar" });
    addBar.appendChild(el("span", { text: "+" }));
    addBar.appendChild(el("span", { text: "Nouvelle tâche" }));
    addBar.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = "Titre de la tâche…";
      input.className = "task-new-input";
      addBar.style.display = "none";
      list.insertBefore(input, addBar);
      input.focus();

      let submitted = false;
      async function submit() {
        if (submitted) return;
        submitted = true;
        const text = input.value.trim();
        input.remove();
        addBar.style.display = "";
        if (!text) return;
        try {
          const created = await J.api.post("/api/tasks", { text });
          const t = { id: created.id, label: created.text, done: false, src: "NOTION" };
          const empty = list.querySelector(".j-empty");
          if (empty) empty.remove();
          list.insertBefore(buildTaskRow(t, list), addBar);
        } catch (_) {}
      }

      input.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); submit(); }
        if (e.key === "Escape") { submitted = true; input.remove(); addBar.style.display = ""; }
      });
      input.addEventListener("blur", submit);
    });
    list.appendChild(addBar);

    const done = tasks.filter(t => t.done).length;
    const wrap = el("div");
    wrap.appendChild(ghostSec("Tâches du jour", "Notion", null, list));

    const page = pageWrapper(
      "taches",
      "Les choses à faire",
      tasks.length ? done + " / " + tasks.length + " terminées" : null,
      wrap
    );
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Analytics ───────── */
  async function renderAnalytics() {
    const wrap = el("div", { style: { display: "flex", flexDirection: "column", gap: "44px" } });

    const globex = await _loadGlobexAnalytics();
    if (globex) {
      const sig = globex.signals || {};
      const kpi = _renderGlobexKpiStrip(sig);
      if (kpi) wrap.appendChild(ghostSec(
        "Plateforme Globex",
        (globex.kernel_version || "globex") + " · " + (globex.generated_at ? J.fmt.relTime(globex.generated_at) : ""),
        el("span", { class: "badge badge--globex", text: "GLOBEX" }),
        kpi
      ));

      const cat = globex.catalog || {};
      const catGrid = el("div", { class: "catalog-grid" });
      const catKpis = [
        { lbl: "Outils catalogue", val: (cat.registered_count || 0) + " / " + (cat.target_count || 62) },
        { lbl: "Catalogue complet", val: cat.complete ? "Oui" : "Non" },
        { lbl: "Missions actives", val: (globex.missions && globex.missions.active) || 0 },
        { lbl: "Approbations", val: (globex.approvals && globex.approvals.pending) || 0 },
      ];
      catKpis.forEach(k => {
        const card = el("div", { class: "kpi-card" });
        card.appendChild(el("div", { class: "kpi-lbl", text: k.lbl }));
        card.appendChild(el("div", { class: "kpi-val kpi-val--sm", text: String(k.val) }));
        catGrid.appendChild(card);
      });
      wrap.appendChild(ghostSec("Catalogue agent", cat.complete ? "62 outils prêts" : "Incomplet", null, catGrid));

      const groups = cat.groups || {};
      const groupList = el("div", { class: "catalog-groups" });
      Object.keys(groups).sort().forEach(name => {
        const row = el("div", { class: "row-stripe" });
        const inner = el("div", { class: "row-stripe-inner" });
        inner.appendChild(el("div", { class: "row-stripe-title", text: name }));
        inner.appendChild(el("div", { class: "row-stripe-meta", text: groups[name] + " outil(s)" }));
        row.appendChild(inner);
        groupList.appendChild(row);
      });
      if (Object.keys(groups).length) {
        wrap.appendChild(ghostSec("Répartition par groupe", null, null, groupList));
      }

      const pro = globex.proactive || {};
      const proBox = el("div");
      proBox.appendChild(el("p", {
        text: (pro.enabled ? "Scheduler actif" : "Scheduler inactif")
          + (pro.interval_seconds ? " · cycle " + pro.interval_seconds + "s" : ""),
      }));
      if (pro.last_run_at) {
        proBox.appendChild(el("p", { text: "Dernier scan : " + J.fmt.relTime(pro.last_run_at) }));
      }
      wrap.appendChild(ghostSec("Surveillance proactive", "Phase 4", el("span", { class: "badge badge--sla", text: "PROACTIF" }), proBox));
    }

    let jarvisData = null;
    try { jarvisData = await J.api.get("/api/analytics/jarvis?days=30"); } catch (_) {}

    if (jarvisData) {
      const kpiGrid = el("div", { class: "kpi-strip" });
      const kpis = [
        { lbl: "Requêtes 30j", val: jarvisData.total_calls||0, unit: "" },
        { lbl: "Coût 30j",     val: jarvisData.total_cost ? "$"+jarvisData.total_cost.toFixed(2) : "—", unit: "" },
        { lbl: "Tokens",       val: jarvisData.total_tokens||0, unit: "" },
      ];
      kpis.forEach(k => {
        const card = el("div", { class: "kpi-card" });
        card.appendChild(el("div", { class: "kpi-lbl", text: k.lbl }));
        card.appendChild(el("div", { class: "kpi-val", text: typeof k.val === "number" ? J.fmt.num(k.val) : k.val }));
        kpiGrid.appendChild(card);
      });
      wrap.appendChild(ghostSec("Jarvis LLM", "30 derniers jours", null, kpiGrid));
    }

    if (!globex && !jarvisData) {
      wrap.appendChild(el("div", { class: "j-empty", text: "Aucune donnée analytics disponible" }));
    }

    const page = pageWrapper("analytics", "Métriques & signaux", null, wrap);
    root.innerHTML = "";
    root.appendChild(page);
  }

  /* ───────── Router ───────── */
  const RENDERERS = {
    apercu:      renderApercu,
    initiatives: renderInitiatives,
    missions:    renderMissions,
    taches:      renderTaches,
    analytics:   renderAnalytics,
  };

  function navigate(pageId) {
    _activePage = pageId;
    // Update rooms nav
    const nav = document.getElementById("j-rooms-pages");
    if (nav) {
      Array.from(nav.querySelectorAll("button")).forEach(b => {
        b.dataset.active = b.querySelector(".lbl") && b.querySelector(".lbl").textContent === PAGES.find(p=>p.id===pageId)?.label ? "true" : "false";
      });
      // More reliable: check by index
      const btns = Array.from(nav.querySelectorAll("button"));
      const idx = PAGES.findIndex(p => p.id === pageId);
      btns.forEach((b, i) => b.dataset.active = i === idx ? "true" : "false");
    }
    const fn = RENDERERS[pageId];
    if (fn) { root.innerHTML = ""; fn(); }
  }

  /* ───────── Init ───────── */
  J.mountAtmosphere();

  J.mountRooms({
    mode: "workspace",
    pages: PAGES,
    activePage: _activePage,
    onNav: (id) => navigate(id),
  });

  J.registerCommands(PAGES.map(p => ({
    kind: "nav", id: "ws-" + p.id, group: "Pilotage",
    title: p.label, glyph: "→",
    run: () => navigate(p.id),
  })));

  // Kick off
  renderApercu();

  let _wsRefreshTimer = null;
  function _scheduleWorkspaceRefresh() {
    if (_wsRefreshTimer) clearInterval(_wsRefreshTimer);
    _wsRefreshTimer = setInterval(() => {
      if (_activePage === "apercu") renderApercu();
      else if (_activePage === "initiatives") renderInitiatives();
    }, 90000);
  }
  _scheduleWorkspaceRefresh();
})();
