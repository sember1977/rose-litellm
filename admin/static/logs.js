// Prompt-Logs Frontend — laedt Key-Liste, setzt aktiven Logging-Key,
// liest initiale Eintraege und streamt neue via SSE.

const $ = (sel) => document.querySelector(sel);

const state = {
  entries: [],       // neueste zuerst
  maxEntries: 500,
  activeAlias: "",
};

async function api(path, opts) {
  const r = await fetch(path, opts || {});
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return await r.json();
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().slice(11, 19);
  } catch { return iso; }
}

function excerpt(s, max = 90) {
  if (!s) return "";
  s = String(s).replace(/\s+/g, " ").trim();
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

function promptExcerpt(entry) {
  const msgs = entry.messages || [];
  // Letzte user-Message bevorzugen
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m && m.role === "user") {
      const c = typeof m.content === "string" ? m.content :
        (Array.isArray(m.content) ? m.content.map(x => x.text || "").join(" ") : "");
      if (c) return excerpt(c);
    }
  }
  // Fallback: erste Message
  const first = msgs[0];
  if (first) {
    const c = typeof first.content === "string" ? first.content : JSON.stringify(first.content);
    return excerpt(c);
  }
  return "";
}

function totalTokens(entry) {
  const u = entry.usage || {};
  return u.total_tokens != null ? u.total_tokens : "—";
}

function renderRow(entry, idx) {
  const tr = document.createElement("tr");
  tr.dataset.idx = String(idx);
  if (entry._logger_error) {
    tr.innerHTML = `
      <td class="mono">${fmtTime(entry.ts)}</td>
      <td colspan="6" class="warn">Logger-Fehler: ${excerpt(entry._logger_error, 200)}</td>`;
    return tr;
  }
  tr.innerHTML = `
    <td class="mono">${fmtTime(entry.ts)}</td>
    <td>${escapeHTML(entry.model || "—")}</td>
    <td class="mono">${escapeHTML(entry.ip || "—")}</td>
    <td class="excerpt" title="${escapeAttr(promptExcerpt(entry))}">${escapeHTML(promptExcerpt(entry))}</td>
    <td class="excerpt" title="${escapeAttr(excerpt(entry.response || "", 200))}">${escapeHTML(excerpt(entry.response || ""))}</td>
    <td class="mono">${totalTokens(entry)}</td>
    <td class="mono">${entry.duration_ms != null ? entry.duration_ms : "—"}</td>`;
  tr.addEventListener("click", () => openModal(idx));
  return tr;
}

function escapeHTML(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeAttr(s) { return escapeHTML(s); }

function renderAll() {
  const tbody = $("#logs-tbody");
  tbody.innerHTML = "";
  if (state.entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">Warte auf Eintraege…</td></tr>`;
  } else {
    state.entries.forEach((e, i) => tbody.appendChild(renderRow(e, i)));
  }
  $("#count-pill").textContent = `${state.entries.length} Eintraege`;
}

function prependEntry(entry) {
  state.entries.unshift(entry);
  if (state.entries.length > state.maxEntries) state.entries.length = state.maxEntries;
  const tbody = $("#logs-tbody");
  // Falls Placeholder noch drin
  if (tbody.querySelector("td.muted")) tbody.innerHTML = "";
  const row = renderRow(entry, 0);
  tbody.insertBefore(row, tbody.firstChild);
  // Indizes der bestehenden Rows korrigieren
  Array.from(tbody.querySelectorAll("tr")).forEach((tr, i) => { tr.dataset.idx = String(i); });
  $("#count-pill").textContent = `${state.entries.length} Eintraege`;
  if ($("#auto-scroll").checked) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function openModal(idx) {
  const e = state.entries[idx];
  if (!e) return;
  $("#modal-title").textContent = `Eintrag ${e.ts || ""}`;
  const usage = e.usage || {};
  $("#modal-meta").textContent =
    `Alias: ${e.alias || "—"} · Modell: ${e.model || "—"} · IP: ${e.ip || "—"}` +
    ` · Tokens: in=${usage.prompt_tokens ?? "—"} out=${usage.completion_tokens ?? "—"} total=${usage.total_tokens ?? "—"}` +
    ` · Dauer: ${e.duration_ms != null ? e.duration_ms + " ms" : "—"}`;
  $("#modal-messages").textContent = JSON.stringify(e.messages || [], null, 2);
  $("#modal-response").textContent = e.response || "(leer)";
  $("#modal-bg").classList.add("show");
}

function closeModal() { $("#modal-bg").classList.remove("show"); }

function updateStatusPill(alias) {
  state.activeAlias = alias || "";
  const pill = $("#status-pill");
  const txt = $("#status-text");
  if (alias) {
    pill.classList.add("on"); pill.classList.remove("off");
    txt.textContent = `Aktiv: ${alias}`;
  } else {
    pill.classList.add("off"); pill.classList.remove("on");
    txt.textContent = "Aus";
  }
  // Select syncen
  const sel = $("#key-select");
  if (sel && sel.value !== (alias || "")) sel.value = alias || "";
}

async function loadKeys() {
  try {
    const data = await api("/api/keys");
    const sel = $("#key-select");
    const current = state.activeAlias;
    // Reset
    sel.innerHTML = `<option value="">— kein Key (Logging aus) —</option>`;
    const aliases = new Set();
    (data.keys || []).forEach(k => {
      const a = k.alias && k.alias !== "—" ? k.alias : null;
      if (a) aliases.add(a);
    });
    Array.from(aliases).sort().forEach(a => {
      const opt = document.createElement("option");
      opt.value = a; opt.textContent = a;
      sel.appendChild(opt);
    });
    if (current) sel.value = current;
  } catch (e) {
    console.error("loadKeys", e);
  }
}

async function loadActive() {
  try {
    const data = await api("/api/logs/active");
    updateStatusPill(data.alias || "");
    $("#logfile-hint").textContent = data.logfile
      ? `Schreibt nach /data/logs/${data.logfile}`
      : "Keine Logdatei — Logging aus.";
  } catch (e) {
    console.error("loadActive", e);
  }
}

async function loadInitialEntries() {
  try {
    const data = await api("/api/logs/list?limit=100");
    state.entries = data.entries || [];
    renderAll();
  } catch (e) {
    console.error("loadInitial", e);
  }
}

async function setActive(alias) {
  await api("/api/logs/active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alias }),
  });
  updateStatusPill(alias);
  $("#logfile-hint").textContent = alias
    ? `Logging gestartet fuer "${alias}". Eintraege erscheinen unten.`
    : "Logging gestoppt.";
  // Bei Wechsel: neu laden
  await loadInitialEntries();
}

let evtSource = null;

function startStream() {
  if (evtSource) try { evtSource.close(); } catch {}
  evtSource = new EventSource("/api/logs/stream");
  evtSource.addEventListener("entry", (ev) => {
    try {
      const obj = JSON.parse(ev.data);
      prependEntry(obj);
    } catch (e) { console.warn("parse entry", e); }
  });
  evtSource.addEventListener("active", (ev) => {
    try {
      const obj = JSON.parse(ev.data);
      const newAlias = obj.alias || "";
      if (newAlias !== state.activeAlias) {
        updateStatusPill(newAlias);
        loadInitialEntries();
        loadActive();
      }
    } catch (e) {}
  });
  evtSource.onerror = () => {
    // Reconnect nach kurzer Pause
    setTimeout(startStream, 3000);
  };
}

function wireUI() {
  $("#apply-btn").addEventListener("click", async () => {
    const v = $("#key-select").value;
    await setActive(v);
  });
  $("#stop-btn").addEventListener("click", async () => {
    $("#key-select").value = "";
    await setActive("");
  });
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-bg").addEventListener("click", (e) => {
    if (e.target.id === "modal-bg") closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

(async function init() {
  wireUI();
  await loadKeys();
  await loadActive();
  await loadInitialEntries();
  startStream();
})();
