# Rose LiteLLM Gateway

**Zweck:** Die LLMs auf dem Spark (vLLM-served Qwen3-Next + nomic-embed) und
ausgewaehlte Cloud-Modelle (Gemini, DeepSeek) sind ueber eine OpenAI-kompatible
API aus dem Internet (https://www.sember.de/llm/) fuer externe Tools nutzbar.
Parallel zu Rose, ohne die Rose-UI zu beruehren.

**Repo:** https://github.com/sember1977/rose-litellm  ·  **Deploy:** `/home/sember/rose-litellm/` auf Spark

---

## Architektur

```
Internet
    |
    | HTTPS (443, Caddy TLS, Let's Encrypt)
    v
+-------------------------------+
| Caddy                         |
|  www.sember.de/*       -> Rose|
|  www.sember.de/llm/*   -> 4000|
+-------------------------------+
              |
              v
+----------------------------+   +---------------------+
| rose-litellm  :4000        |<->| rose-litellm-db     |
|  LiteLLM Proxy             |   | Postgres (persist.) |
|  - Modell-Routing          |   | - Keys + Spend      |
|  - Auth (API-Keys, optional|   +---------------------+
|    siehe Sicherheit unten) |
+----------------------------+
              |
              +-----> rose-vllm-next   :8014  (Qwen3-Next-80B-A3B-Instruct-AWQ-4bit)
              +-----> rose-vllm-embed  :8013  (nomic-embed-text-v1.5)
              +-----> Cloud:  Gemini API, DeepSeek API
              |
              +-----> chemicals-rag-svc :8021 (RAG-Wrapper -> qwen-chemicals)

+--------------------+
| rose-litellm-admin |  LAN-only (192.168.1.155:4001)
|  - Key-UI          |  - keine externe Erreichbarkeit
|  - Status          |
+--------------------+
```

**Container im Compose (`/home/sember/rose-litellm/docker-compose.yml`):**
- `rose-litellm-db` — eigener Postgres (Volume `litellm_pgdata`)
- `rose-litellm` — LiteLLM Proxy (Port 4000 extern via Caddy)
- `rose-litellm-admin` — Key-/Status-UI (LAN-only)

**Geteilte Backends (laufen NICHT in diesem Compose):**
- `rose-vllm-next`, `rose-vllm-embed` — eigene Compose-Dateien
- `rose-qdrant` — Vector-Store (gemeinsam genutzt)
- `chemicals-rag-svc` — RAG-Service fuer Gefahrstoff-Domain (eigenes Repo: https://github.com/sember1977/chemicals-rag-svc), exponiert das Modell `qwen-chemicals`

---

## Modelle

| Alias | Backend | Zweck |
|---|---|---|
| `qwen3.6` | vLLM `qwen3-next` (Qwen3-Next-80B-A3B-Instruct-AWQ-4bit) | General-Chat, Tool-Use, 256k Context |
| `qwen3.6-vibe` | vLLM `qwen3-next` | Gleiche Engine, fuer Rose-Vibe-spezifischen System-Prompt reserviert |
| `nomic-embed` | vLLM `nomic-embed` (nomic-embed-text-v1.5) | Embeddings, 768-dim |
| `gemini-pro-latest` | Google Gemini Pro | Groesseres Reasoning, 1M context |
| `gemini-flash-latest` | Google Gemini Flash | Schnell + guenstig + Vision |
| `deepseek-v4-pro` | DeepSeek V4-Pro | Hoechster Agentic-Score, 1M context |
| `deepseek-v4-flash` | DeepSeek V4-Flash | Schnell + guenstig fuer Routine |
| `qwen-chemicals` | RAG-Wrapper vor `qwen3-next` | Gefahrstoff-Betriebsanweisungen + EMKG-Bewertung (siehe `chemicals-rag-svc`) |

Capabilities (Vision/Function-Calling/Reasoning) und Token-Limits stehen pro
Modell in `litellm_config.yaml` unter `model_info`. Verifikation:

```bash
curl -s -H "Authorization: Bearer $MASTER_KEY" http://127.0.0.1:4000/v1/models
```

**Hinweis:** `qwen3.6` ist im Config zwar mit `supports_vision: true` markiert,
aber Qwen3-Next-80B ist textbasiert. Echtes Vision liefert `gemini-flash-latest`.

---

## Modelle aendern

```bash
vim /home/sember/rose-litellm/litellm_config.yaml
docker compose restart litellm
```

Neue vLLM-Backends muessen unabhaengig deployed werden (eigenes Compose,
gemeinsames Docker-Netz `rose-litellm_default`).

---

## Sicherheit — WICHTIGER HINWEIS

**Aktueller Stand:** Auth-Erzwingung ist auf Proxy-Ebene **nicht aktiv**.
Der Wert `master_key: os.environ/MASTER_KEY` in `litellm_config.yaml` referenziert
eine Env-Var, die im Container leer ist (Container-Env heisst tatsaechlich
`LITELLM_MASTER_KEY`). LiteLLM laesst dadurch Anfragen ohne / mit beliebigem Key
durch — auch ueber www.sember.de/llm/ aus dem Internet erreichbar.

**Bevor das System produktiv mit Cloud-Modellen (DeepSeek/Gemini) genutzt wird,
muss Auth aktiviert werden.** Eine Zeilenaenderung:

```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY    # vorher: os.environ/MASTER_KEY
```

Und sicherstellen, dass alle Konsumenten (rose-vibe, rose-spark, etc.) gueltige
API-Keys in ihren `.env`-Dateien haben (NICHT die Platzhalter `sk-rose-CHANGE_ME`).

### Was bereits geschuetzt ist

- Port 4001 (Admin-UI) nur an LAN-IP gebunden — extern nicht erreichbar
- TLS via Let's Encrypt (Caddy) auf www.sember.de
- API-Keys werden bcrypt-gehasht in Postgres gespeichert (LiteLLM-intern)
- vLLM-Backends nur via Docker-Netz erreichbar, nicht extern exponiert

---

## API-Keys verwalten

### Via Admin-UI (empfohlen)

Im LAN: **http://192.168.1.155:4001** -> "Neuer Key" -> Modelle scopen ->
Klartext **einmalig** kopieren -> in Tool eintragen.

### Via curl

```bash
MASTER=$(grep MASTER_KEY /home/sember/rose-litellm/.env | cut -d= -f2)

# Erstellen
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"key_alias":"MyTool","models":["qwen3.6","nomic-embed"],"max_budget":20,"budget_duration":"30d"}'

# Loeschen
curl -X POST http://localhost:4000/key/delete \
  -H "Authorization: Bearer $MASTER" -H "Content-Type: application/json" \
  -d '{"keys":["sk-..."]}'
```

Plaintext eines Keys laesst sich **nicht nachtraeglich** abrufen — nur einmalig
beim Erzeugen. LiteLLM speichert nur Hashes.

---

## URL-Konvention in verschiedenen Tools

| Tool | Base-URL-Feld |
|---|---|
| OpenAI Python SDK, Continue.dev, Aider, Zed, Cursor | `https://www.sember.de/llm/v1` |
| Chatbox, manche iOS-Apps | `https://www.sember.de/llm` (ohne /v1) |
| curl | `https://www.sember.de/llm/v1/chat/completions` |

## Tool-Configs (Auswahl)

### Continue.dev (`~/.continue/config.json`)

```json
{
  "models": [
    {
      "title": "Qwen3.6 @ Rose",
      "provider": "openai",
      "model": "qwen3.6",
      "apiBase": "https://www.sember.de/llm/v1",
      "apiKey": "sk-rose-..."
    }
  ],
  "embeddingsProvider": {
    "provider": "openai",
    "model": "nomic-embed",
    "apiBase": "https://www.sember.de/llm/v1",
    "apiKey": "sk-rose-..."
  }
}
```

### Python (OpenAI SDK)

```python
from openai import OpenAI
client = OpenAI(base_url="https://www.sember.de/llm/v1", api_key="sk-rose-...")
resp = client.chat.completions.create(
    model="qwen3.6",
    messages=[{"role": "user", "content": "Hallo"}],
)
print(resp.choices[0].message.content)
```

Aider, Zed, Cursor, Cline analog — siehe LiteLLM-Dokumentation.

---

## Wartung

### LiteLLM-Update

```bash
cd /home/sember/rose-litellm
docker compose pull litellm
docker compose up -d litellm
```

Prisma migriert die DB beim Start automatisch.

### Backup

```bash
docker exec rose-litellm-db pg_dump -U litellm litellm > litellm-backup-$(date +%Y%m%d).sql
```

### Logs

```bash
docker logs rose-litellm --tail 50
docker logs rose-litellm-admin --tail 50
sudo tail -f /var/log/caddy/access.log | grep '/llm/'
```

### Schnelltest

```bash
KEY=sk-rose-...
curl https://www.sember.de/llm/v1/models -H "Authorization: Bearer $KEY"
curl -X POST https://www.sember.de/llm/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen3.6","messages":[{"role":"user","content":"Hi"}]}'
```

---

## Troubleshooting

| Symptom | Ursache | Fix |
|---|---|---|
| `401 Unauthorized` | Key falsch / abgelaufen | In Admin-UI neuen Key |
| `404 Not Found` auf `/llm/v1/...` | Caddy-Config nicht geladen | `sudo systemctl reload caddy` |
| `502 Bad Gateway` | LiteLLM-Container down | `docker logs rose-litellm` |
| `model not found` | Alias-Name falsch | Liste per `/v1/models` pruefen |
| Langsam beim ersten Request | vLLM-Modell nicht im RAM | erstes Laden ~30-60s, dann flott |

---

## Erweiterungen

- **TTL-Cleanup** alter Keys via Cron
- **IP-Whitelist** pro Key (LiteLLM `allowed_ips`)
- **Email-Report** wochenweise aus den `LiteLLM_Daily*Spend`-Tabellen
- **Cloudflare-Tunnel** statt offenem Port 443
