// Rose LiteLLM Dashboard

const $ = (id) => document.getElementById(id);

function fmt(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return String(n);
}

function fmtSpend(s) {
  if (s == null || s === 0) return '—';
  if (s < 0.01) return '<0,01 €';
  return s.toFixed(2) + ' €';
}

function fmtDuration(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return Math.round(ms) + ' ms';
  return (ms / 1000).toFixed(1) + ' s';
}

function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function statusBadge(status) {
  const cls = status === 'success' ? 'status-ok' : 'status-bad';
  return `<span class="${cls}">${status}</span>`;
}

async function loadToday() {
  try {
    const r = await fetch('/api/dashboard/today');
    const d = await r.json();

    if (d.error) {
      $('today-error').textContent = 'Fehler: ' + d.error;
      $('today-error').classList.remove('hidden');
      return;
    }
    $('today-error').classList.add('hidden');

    const today = new Date().toLocaleDateString('de-DE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    $('today-date').textContent = today + ' · ' + d.total_requests + ' Requests insgesamt';

    const tbody = document.querySelector('#today-table tbody');
    tbody.innerHTML = '';

    const models = d.models || [];
    if (models.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">Heute noch keine Requests.</td></tr>';
      $('today-total').textContent = '';
      return;
    }

    models.forEach(m => {
      const dot = m.active_last_10min
        ? '<span class="dot active" title="aktiv in den letzten 10 Min">🟢</span>'
        : '<span class="dot" title="inaktiv">⚫</span>';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${dot}</td>
        <td class="model-name">${m.model}</td>
        <td class="num">${m.requests}</td>
        <td class="num">${fmt(m.prompt_tokens)}</td>
        <td class="num">${fmt(m.completion_tokens)}</td>
        <td class="num">${fmtSpend(m.spend)}</td>
      `;
      tbody.appendChild(tr);
    });

    $('today-total').textContent = d.total_requests + ' Requests heute';
  } catch (e) {
    $('today-error').textContent = 'Netzwerkfehler: ' + e.message;
    $('today-error').classList.remove('hidden');
  }
}

async function loadRecent() {
  try {
    const r = await fetch('/api/dashboard/recent');
    const d = await r.json();

    if (d.error) {
      $('recent-error').textContent = 'Fehler: ' + d.error;
      $('recent-error').classList.remove('hidden');
      return;
    }
    $('recent-error').classList.add('hidden');

    const tbody = document.querySelector('#recent-table tbody');
    tbody.innerHTML = '';

    const reqs = d.requests || [];
    if (reqs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="muted">Keine Requests geloggt.</td></tr>';
      return;
    }

    reqs.forEach(req => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${fmtTime(req.startTime)}</td>
        <td class="model-name">${req.model}</td>
        <td class="muted small">${req.key_alias}</td>
        <td class="num">${fmt(req.prompt_tokens)}</td>
        <td class="num">${fmt(req.completion_tokens)}</td>
        <td class="num">${fmtDuration(req.duration_ms)}</td>
        <td>${statusBadge(req.status)}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    $('recent-error').textContent = 'Netzwerkfehler: ' + e.message;
    $('recent-error').classList.remove('hidden');
  }
}

// Poll /health alle 30s und update die Aktivitaets-Punkte
async function pollHealth() {
  try {
    const r = await fetch('/api/dashboard/health');
    const d = await r.json();
    const activeSet = new Set((d.active_models || []).map(m => m.model));

    document.querySelectorAll('#today-table tbody .dot').forEach(dot => {
      const row = dot.closest('tr');
      const nameEl = row && row.querySelector('.model-name');
      if (!nameEl) return;
      const modelName = nameEl.textContent;
      if (activeSet.has(modelName)) {
        dot.classList.add('active');
        dot.title = 'aktiv in den letzten 10 Min';
        dot.textContent = '🟢';
      } else {
        dot.classList.remove('active');
        dot.title = 'inaktiv';
        dot.textContent = '⚫';
      }
    });
  } catch (_) { /* silently ignore */ }
}

// Initial laden
loadToday();
loadRecent();

// Auto-Refresh: health alle 30s, recent + today alle 60s
setInterval(pollHealth, 30000);
setInterval(loadToday, 60000);
setInterval(loadRecent, 60000);
