/* fils_panel.js — Sessions / fils de conversation (partagé Home + Capacités) */
(function () {
  "use strict";

  function el(tag, attrs, children) {
    const J = window.Jarvis;
    if (J && typeof J.el === "function") return J.el(tag, attrs, children);
    const node = document.createElement(tag);
    if (attrs) {
      Object.entries(attrs).forEach(([k, v]) => {
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k === "html") node.innerHTML = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
        else node.setAttribute(k, v);
      });
    }
    (children || []).forEach((c) => { if (c) node.appendChild(c); });
    return node;
  }

  function assistantLabel() {
    return "Fedex-v0";
  }

  /**
   * @param {HTMLElement} container
   * @param {{ api?: object, notify?: Function, limit?: number, compact?: boolean }} opts
   * @returns {Promise<number>} nombre de sessions affichées
   */
  async function mountFilsPanel(container, opts) {
    opts = opts || {};
    const api = opts.api || (window.Jarvis && window.Jarvis.api);
    const notify = opts.notify || (window.Jarvis && window.Jarvis.notify) || function () {};
    const limit = opts.limit == null ? 20 : opts.limit;
    const compact = !!opts.compact;

    if (!container || !api) return 0;
    container.innerHTML = "";
    if (compact) container.classList.add("fils-panel--compact");

    let sessions = [];
    try {
      sessions = await api.get("/api/sessions");
    } catch (_) {
      container.appendChild(el("div", { class: "fils-empty", text: "Impossible de charger les fils." }));
      return 0;
    }

    const list = el("div", { class: "fils-list" });
    if (!sessions.length) {
      list.appendChild(el("div", { class: "fils-empty", text: "Aucune session récente" }));
      container.appendChild(list);
      return 0;
    }

    const shown = sessions.slice(0, limit);
    shown.forEach((s) => {
      const row = el("div", { class: "session-row" });
      row.appendChild(el("div", { class: "sess-id t-mono", text: (s.id || "").slice(0, 6).toUpperCase() }));

      const preview = el("div");
      const titleEl = el("div", { class: "sess-preview", text: s.title || s.preview || "—" });
      preview.appendChild(titleEl);
      preview.appendChild(el("div", {
        class: "sess-meta",
        text: (s.message_count || 0) + " messages",
      }));
      row.appendChild(preview);
      row.appendChild(el("div", { class: "sess-date", text: s.date || "" }));

      const viewBtn = el("button", { class: "m-btn", text: "Voir" });
      const renameBtn = el("button", { class: "m-btn", text: "Renommer" });
      const delBtn = el("button", { class: "m-btn m-btn--danger", text: "✕" });
      delBtn.title = "Supprimer ce fil";
      const acts = el("div", { class: "mem-btn-row" });
      acts.appendChild(viewBtn);
      acts.appendChild(renameBtn);
      acts.appendChild(delBtn);
      row.appendChild(acts);
      list.appendChild(row);

      const viewer = el("div", { class: "sess-viewer" });
      const msgList = el("div", { class: "sess-msg-list" });
      const closeViewBtn = el("button", { class: "m-btn", text: "Fermer" });
      viewer.appendChild(msgList);
      viewer.appendChild(closeViewBtn);
      list.appendChild(viewer);

      viewBtn.addEventListener("click", async () => {
        if (viewer.classList.contains("open")) {
          viewer.classList.remove("open");
          viewBtn.textContent = "Voir";
          return;
        }
        editor.classList.remove("open");
        renameBtn.textContent = "Renommer";
        viewBtn.textContent = "…";
        viewBtn.disabled = true;
        try {
          const msgs = await api.get("/api/sessions/" + encodeURIComponent(s.id) + "/messages?limit=100");
          msgList.innerHTML = "";
          if (!msgs.length) {
            msgList.appendChild(el("div", { class: "sess-msg-empty", text: "Aucun message." }));
          } else {
            msgs.forEach((m) => {
              const bubble = el("div", { class: "sess-bubble sess-bubble--" + (m.role === "user" ? "user" : "assistant") });
              const label = el("div", {
                class: "sess-bubble-role",
                text: m.role === "user" ? "Toi" : assistantLabel(),
              });
              const body = el("div", { class: "sess-bubble-body", text: m.content || "" });
              bubble.appendChild(label);
              bubble.appendChild(body);
              msgList.appendChild(bubble);
            });
          }
          viewer.classList.add("open");
          setTimeout(() => viewer.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
        } catch (e) {
          notify({ kind: "error", text: e.message || "Erreur" });
        }
        viewBtn.textContent = "Voir";
        viewBtn.disabled = false;
      });

      closeViewBtn.addEventListener("click", () => {
        viewer.classList.remove("open");
        viewBtn.textContent = "Voir";
      });

      const editor = el("div", { class: "sess-rename-editor" });
      const inp = el("input", { class: "sess-rename-input", type: "text" });
      inp.value = s.title || s.preview || "";
      inp.placeholder = "Nouveau titre…";
      editor.appendChild(inp);
      const saveBtn = el("button", { class: "m-btn m-btn--save", text: "Sauvegarder" });
      const closeBtn = el("button", { class: "m-btn", text: "Annuler" });
      const btnRow = el("div", { class: "mem-btn-row" });
      btnRow.appendChild(saveBtn);
      btnRow.appendChild(closeBtn);
      editor.appendChild(btnRow);
      list.appendChild(editor);

      renameBtn.addEventListener("click", () => {
        const open = editor.classList.contains("open");
        if (!open) {
          viewer.classList.remove("open");
          viewBtn.textContent = "Voir";
        }
        editor.classList.toggle("open", !open);
        renameBtn.textContent = open ? "Renommer" : "Annuler";
        if (!open) {
          inp.focus();
          inp.select();
        }
      });

      closeBtn.addEventListener("click", () => {
        editor.classList.remove("open");
        renameBtn.textContent = "Renommer";
      });

      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") saveBtn.click();
        if (e.key === "Escape") closeBtn.click();
      });

      saveBtn.addEventListener("click", async () => {
        const newTitle = inp.value.trim();
        if (!newTitle) return;
        const orig = saveBtn.textContent;
        saveBtn.textContent = "…";
        saveBtn.disabled = true;
        try {
          await api.put("/api/sessions/" + encodeURIComponent(s.id) + "/title", { title: newTitle });
          titleEl.textContent = newTitle;
          editor.classList.remove("open");
          renameBtn.textContent = "Renommer";
          notify({ kind: "success", text: "Fil renommé" });
        } catch (e) {
          notify({ kind: "error", text: e.message || "Erreur" });
          saveBtn.textContent = "✗ Erreur";
        }
        setTimeout(() => {
          saveBtn.textContent = orig;
          saveBtn.disabled = false;
        }, 1800);
      });

      delBtn.addEventListener("click", async () => {
        if (!confirm("Supprimer ce fil définitivement ?")) return;
        delBtn.disabled = true;
        try {
          await api.delete("/api/sessions/" + encodeURIComponent(s.id));
          row.remove();
          viewer.remove();
          editor.remove();
          notify({ kind: "success", text: "Fil supprimé" });
        } catch (e) {
          notify({ kind: "error", text: e.message || "Erreur" });
          delBtn.disabled = false;
        }
      });
    });

    container.appendChild(list);
    return shown.length;
  }

  window.FilsPanel = { mount: mountFilsPanel };
})();
