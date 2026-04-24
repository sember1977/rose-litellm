// Rose LiteLLM Admin — minimales Frontend

const $ = (id) => document.getElementById(id);

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    $('status-health').textContent = d.healthy ? '✓ OK' : '✗ Fehler';
    $('status-health').className = 'v ' + (d.healthy ? 'status-ok' : 'status-bad');
    $('status-version').textContent = d.litellm_version || '—';
    $('status-models').textContent = (d.models || []).join(', ') || '—';
    $('model-ids').innerHTML = (d.models || []).map(m =>
      `<code>${m}</code>${modelHint(m)}`
    ).join('<br>') || '—';

    // Modelle ins Select einfuegen
    const sel = $('f-models');
    sel.innerHTML = '';
    (d.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      opt.selected = true;
      sel.appendChild(opt);
    });

    updateExamples(d.api_base_external || 'https://www.sember.de/llm/v1', d.models || []);
  } catch (e) {
    $('status-health').textContent = '✗ Admin kann LiteLLM nicht erreichen';
    $('status-health').className = 'v status-bad';
  }
}

function modelHint(m) {
  const hints = {
    'qwen3.6':       ' <span class="muted">— schneller Chat, kein Thinking</span>',
    'qwen3.6-think': ' <span class="muted">— mit sichtbarem Reasoning (langsamer)</span>',
    'qwen3-coder':   ' <span class="muted">— Coding-optimiert</span>',
    'nomic-embed':   ' <span class="muted">— Embeddings (Vector-Search)</span>',
  };
  return hints[m] || '';
}

function updateExamples(apibaseWithV1, models) {
  const model = models.find(m => m === 'qwen3-coder') || models[0] || 'qwen3.6';
  const apibaseNoV1 = apibaseWithV1.replace(/\/v1\/?$/, '');

  $('example-continue').textContent = JSON.stringify({
    models: [{
      title: 'Rose ' + model,
      provider: 'openai',
      model,
      apiBase: apibaseWithV1,
      apiKey: 'sk-…'
    }]
  }, null, 2);

  $('example-aider').textContent =
    `aider --openai-api-base ${apibaseWithV1} \\\n       --openai-api-key sk-… \\\n       --model openai/${model}`;

  $('example-chatbox').textContent =
`Provider:  OpenAI API (oder "OpenAI Compatible")
API Host:  ${apibaseNoV1}         ← OHNE /v1
API Key:   sk-…
Model:     ${model}               ← manuell eintippen`;

  $('example-zed').textContent = JSON.stringify({
    assistant: {
      default_model: {
        provider: 'openai_compatible',
        api_url: apibaseWithV1,
        api_key_env: 'OPENAI_API_KEY',
        available_models: models.map(m => ({ name: m, display_name: m, max_tokens: 16384 }))
      }
    }
  }, null, 2);

  $('example-curl').textContent =
    `curl -X POST ${apibaseWithV1}/chat/completions \\\n  -H "Authorization: Bearer sk-…" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model":"${model}","messages":[{"role":"user","content":"Hallo"}]}'`;
}

async function loadKeys() {
  try {
    const r = await fetch('/api/keys');
    const d = await r.json();
    const list = $('keys-list');
    list.innerHTML = '';
    const keys = d.keys || [];
    if (keys.length === 0) {
      list.innerHTML = `<li><span>${d.error ? 'Fehler: ' + d.error : 'Noch keine Keys. Erstelle unten einen.'}</span></li>`;
      return;
    }
    keys.forEach(k => {
      const name = k.alias || '(ohne Name)';
      const prefix = k.token_prefix || '—';
      const models = (k.models || []).join(', ') || 'alle';
      const rpm = k.rpm_limit != null ? `${k.rpm_limit} rpm` : '∞ rpm';
      const spend = typeof k.spend === 'number' ? k.spend.toFixed(3) : '—';
      const li = document.createElement('li');
      li.innerHTML = `<div>
        <b>${name}</b> · <span class="muted">${prefix}</span><br>
        <span class="muted small">${models} · ${rpm} · spend: ${spend}</span>
      </div>
      <button class="revoke" data-token="${k.token}">widerrufen</button>`;
      list.appendChild(li);
    });
    list.querySelectorAll('.revoke').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Key wirklich widerrufen?')) return;
        await fetch('/api/keys/delete', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: btn.dataset.token })
        });
        loadKeys();
      });
    });
  } catch (e) {
    $('keys-list').innerHTML = `<li><span>Fehler: ${e.message}</span></li>`;
  }
}

$('key-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const models = Array.from($('f-models').selectedOptions).map(o => o.value);
  const body = {
    alias: $('f-alias').value,
    rpm_limit: $('f-rpm').value ? parseInt($('f-rpm').value, 10) : undefined,
    duration: $('f-dur').value || undefined,
  };
  if (models.length > 0) body.models = models;

  const r = await fetch('/api/keys', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) {
    alert('Fehler: ' + (await r.text()));
    return;
  }
  const d = await r.json();
  const key = d.key || '';
  $('new-key-text').textContent = key;
  $('new-key-result').classList.remove('hidden');
  loadKeys();
});

// Copy-Handler
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.copy');
  if (!btn) return;
  const target = document.querySelector(btn.dataset.copy);
  if (!target) return;
  navigator.clipboard.writeText(target.textContent || target.innerText);
  const orig = btn.textContent;
  btn.textContent = 'kopiert!';
  setTimeout(() => btn.textContent = orig, 1200);
});

// Initial-Laden
loadStatus();
loadKeys();
setInterval(loadStatus, 30000);
