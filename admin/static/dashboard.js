// Rose LiteLLM Dashboard

const $ = (id) => document.getElementById(id);

// ─── Formatters ──────────────────────────────────────────────────

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

function fmtHour(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

function statusBadge(status) {
  const cls = status === 'success' ? 'status-ok' : 'status-bad';
  return `<span class="${cls}">${status}</span>`;
}

// ─── State ───────────────────────────────────────────────────────

let currentFilter = '';
let chartData = null;

// ─── Chart ───────────────────────────────────────────────────────

const MODEL_COLORS = [
  '#b794f6', // purple
  '#4ade80', // green
  '#fbbf24', // amber
  '#60a5fa', // blue
  '#f87171', // red
  '#c084fc', // violet
  '#34d399', // emerald
  '#fb923c', // orange
];

function modelColor(idx) {
  return MODEL_COLORS[idx % MODEL_COLORS.length];
}

function drawChart(buckets, models) {
  const canvas = $('timeline-canvas');
  const container = canvas.parentElement;
  const legendDiv = $('chart-legend');
  const emptyMsg = $('chart-empty');

  if (!buckets || buckets.length === 0) {
    emptyMsg.classList.remove('hidden');
    canvas.style.display = 'none';
    legendDiv.innerHTML = '';
    return;
  }

  emptyMsg.classList.add('hidden');
  canvas.style.display = '';

  // Determine 24h window
  const now = new Date();
  const start = new Date(now.getTime() - 24 * 3600 * 1000);
  // Round to next full hour for the start
  const windowStart = new Date(start.getFullYear(), start.getMonth(), start.getDate(), start.getHours() + 1, 0, 0, 0);
  const hours = [];
  for (let i = 0; i < 24; i++) {
    hours.push(new Date(windowStart.getTime() + i * 3600 * 1000));
  }

  // Build lookup: "2025-01-15T14:00:00" -> { model -> count }
  const lookup = {};
  for (const b of buckets) {
    const key = b.hour;
    if (!lookup[key]) lookup[key] = {};
    lookup[key][b.model] = (lookup[key][b.model] || 0) + b.requests;
  }

  // Build data matrix: hours[0..23] x models -> count
  const data = hours.map(h => {
    const key = h.toISOString().replace(/\.\d{3}Z$/, '');
    const row = {};
    for (const m of models) {
      row[m] = (lookup[key] && lookup[key][m]) || 0;
    }
    return row;
  });

  // Find max stack height
  let maxStack = 0;
  for (const row of data) {
    let sum = 0;
    for (const m of models) sum += row[m];
    if (sum > maxStack) maxStack = sum;
  }
  if (maxStack === 0) maxStack = 1;

  // Canvas sizing
  const dpr = window.devicePixelRatio || 1;
  const width = container.clientWidth;
  const height = 200;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = width + 'px';
  canvas.style.height = height + 'px';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const padLeft = 38;
  const padRight = 10;
  const padTop = 8;
  const padBottom = 22;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;
  const barGap = 2;
  const barWidth = Math.max(2, (chartW / 24) - barGap);

  ctx.clearRect(0, 0, width, height);

  // Y-axis labels
  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const val = Math.round((maxStack / 4) * i);
    const y = padTop + chartH - (chartH / 4) * i;
    ctx.fillText(String(val), padLeft - 5, y + 3);
    // gridline
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();
  }

  // Bars
  for (let h = 0; h < 24; h++) {
    const x = padLeft + h * (barWidth + barGap);
    let yOffset = padTop + chartH;

    for (let mi = 0; mi < models.length; mi++) {
      const count = data[h][models[mi]];
      if (count === 0) continue;
      const barH = (count / maxStack) * chartH;
      yOffset -= barH;

      ctx.fillStyle = modelColor(mi);
      ctx.fillRect(x, yOffset, barWidth, barH);
    }
  }

  // X-axis labels (every 6 hours)
  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif';
  ctx.textAlign = 'center';
  for (let h = 0; h < 24; h += 6) {
    const x = padLeft + h * (barWidth + barGap) + barWidth / 2;
    ctx.fillText(fmtHour(hours[h].toISOString()), x, height - 4);
  }

  // Mouse: tooltip
  canvas.onmousemove = function(ev) {
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;

    const hoverIdx = Math.floor((mx - padLeft) / (barWidth + barGap));
    if (hoverIdx < 0 || hoverIdx >= 24) {
      canvas.title = '';
      return;
    }

    const h = hours[hoverIdx];
    let parts = [fmtHour(h.toISOString())];
    let total = 0;
    for (const m of models) {
      const c = data[hoverIdx][m];
      if (c > 0) parts.push(m + ': ' + c);
      total += c;
    }
    if (total === 0) parts.push('keine Requests');
    canvas.title = parts.join('\n');
  };

  // Legend
  legendDiv.innerHTML = models.map((m, i) =>
    `<span class="legend-item"><span class="legend-swatch" style="background:${modelColor(i)}"></span>${m}</span>`
  ).join('');
}

// ─── Today ───────────────────────────────────────────────────────

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
      // Fusszeile auf null
      $('today-foot-reqs').textContent = '0';
      $('today-foot-pt').textContent = '0';
      $('today-foot-ct').textContent = '0';
      $('today-foot-spend').textContent = '—';
      return;
    }

    let totalPt = 0;
    let totalCt = 0;

    models.forEach(m => {
      totalPt += m.prompt_tokens;
      totalCt += m.completion_tokens;
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

    // Fusszeile
    $('today-foot-reqs').textContent = fmt(d.total_requests);
    $('today-foot-pt').textContent = fmt(totalPt);
    $('today-foot-ct').textContent = fmt(totalCt);
    $('today-foot-spend').textContent = fmtSpend(d.total_spend);

    $('today-total').textContent = d.total_requests + ' Requests heute · ' + fmtSpend(d.total_spend) + ' Gesamtkosten';
  } catch (e) {
    $('today-error').textContent = 'Netzwerkfehler: ' + e.message;
    $('today-error').classList.remove('hidden');
  }
}

// ─── Recent ──────────────────────────────────────────────────────

async function loadRecent() {
  try {
    let url = '/api/dashboard/recent';
    if (currentFilter) url += '?key_alias=' + encodeURIComponent(currentFilter);

    const r = await fetch(url);
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
      tbody.innerHTML = '<tr><td colspan="7" class="muted">Keine Requests geloggt' + (currentFilter ? ' fuer Key "' + currentFilter + '"' : '') + '.</td></tr>';
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

// ─── Timeline ────────────────────────────────────────────────────

async function loadTimeline() {
  try {
    let url = '/api/dashboard/timeline';
    if (currentFilter) url += '?key_alias=' + encodeURIComponent(currentFilter);

    const r = await fetch(url);
    const d = await r.json();

    if (d.error) {
      $('chart-error').textContent = 'Fehler: ' + d.error;
      $('chart-error').classList.remove('hidden');
      return;
    }
    $('chart-error').classList.add('hidden');

    chartData = d;
    drawChart(d.buckets, d.models);
  } catch (e) {
    $('chart-error').textContent = 'Netzwerkfehler: ' + e.message;
    $('chart-error').classList.remove('hidden');
  }
}

// ─── Key Aliases ─────────────────────────────────────────────────

async function loadKeyAliases() {
  try {
    const r = await fetch('/api/dashboard/key-aliases');
    const d = await r.json();
    const select = $('key-filter');

    const aliases = d.aliases || [];
    aliases.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a;
      opt.textContent = a;
      select.appendChild(opt);
    });
  } catch (_) { /* silently ignore */ }
}

function onFilterChange() {
  currentFilter = $('key-filter').value;
  loadRecent();
  loadTimeline();
}

// ─── Health Poll ─────────────────────────────────────────────────

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

// ─── Init ────────────────────────────────────────────────────────

$('key-filter').addEventListener('change', onFilterChange);

// Initial load
loadToday();
loadRecent();
loadTimeline();
loadKeyAliases();

// Auto-Refresh
setInterval(pollHealth, 30000);
setInterval(loadToday, 60000);
setInterval(loadRecent, 60000);
setInterval(loadTimeline, 120000);  // Chart nur alle 2 Min, da 24h-Daten sich langsam aendern
