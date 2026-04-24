# Rose LiteLLM Gateway

**Zweck:** Die Modelle auf dem Spark (qwen3.6, qwen3-coder, nomic-embed)
sind ueber eine OpenAI-kompatible API aus dem Internet fuer externe Tools
nutzbar. Parallel zu Rose, ohne Rose zu beruehren.

**Nicht fuer:** Integrationsarbeit in die Rose-UI. Rose bleibt unveraendert.

---

## Architektur

```
Internet
    |
    | HTTPS (443, Caddy TLS)
    v
┌──────────────────────────┐
│   Caddy                  │
│   www.sember.de/*        │ -> Rose (wie bisher)
│   www.sember.de/llm/*    │ -> rose-litellm (Port 4000)
└──────────────────────────┘
         |
         v
┌──────────────────────────┐      ┌────────────────────────┐
│   rose-litellm           │ <--> │   rose-litellm-db      │
│   LiteLLM Proxy          │      │   Postgres (persist.)  │
│   - Auth (API-Keys)      │      │   - Keys + Spend       │
│   - Rate-Limit           │      └────────────────────────┘
│   - Request-Routing      │
└──────────────────────────┘
         |
         v                                      (nur LAN,
┌──────────────────────────┐                    Port 4001 an
│   Ollama :11434          │  <- geteilt mit    192.168.1.155)
│   qwen3.6                │     Rose
│   qwen3-coder            │            ┌──────────────────┐
│   nomic-embed-text       │            │ rose-litellm-    │
└──────────────────────────┘            │ admin            │
                                        │  - Key-UI        │
                                        │  - Status        │
                                        │  - Anleitung     │
                                        └──────────────────┘
```

**Drei Container (alle in `/home/sember/rose-litellm/`):**
- `rose-litellm-db` — eigener Postgres (Volume `litellm_pgdata`)
- `rose-litellm` — LiteLLM Proxy (extern ueber Caddy)
- `rose-litellm-admin` — kleine UI (LAN-only, 192.168.1.155:4001)

**Nicht beruehrt:** rose-api, rose-postgres, rose-voice, rose-qdrant, MCP-Bridge, Ollama-Installation.

---

## Installation (bereits erledigt)

### 1. Ordnerstruktur

```
/home/sember/rose-litellm/
├── .env                      # MASTER_KEY, SALT_KEY, POSTGRES_*
├── docker-compose.yml        # 3 Services: postgres, litellm, admin
├── litellm_config.yaml       # Modell-Aliase + Ollama-Mapping
└── admin/
    ├── Dockerfile
    ├── app.py                # FastAPI-Backend
    └── static/
        ├── index.html
        ├── style.css
        └── app.js
```

### 2. .env (Secrets)

```
MASTER_KEY=sk-rose-<32-hex>
SALT_KEY=<32-hex>
POSTGRES_USER=litellm
POSTGRES_PASSWORD=<generiert>
POSTGRES_DB=litellm
```

Rechte: `chmod 600 .env`

### 3. Caddy-Konfig

In `/etc/caddy/Caddyfile` wurde der `www.sember.de`-Block erweitert:

```caddy
www.sember.de {
    ...
    reverse_proxy /ws/voice localhost:8001
    handle_path /llm/* {
        reverse_proxy localhost:4000
    }
    reverse_proxy localhost:8000   # Rose bleibt default
}
```

### 4. Starten

```bash
cd /home/sember/rose-litellm
docker compose up -d
```

### 5. Verifikation

```bash
# Health
curl http://localhost:4000/health/readiness
# -> {"status":"healthy", "db":"connected", ...}

# Admin-UI erreichbar?
curl http://192.168.1.155:4001/api/status
# -> {"healthy":true, "models":[...], ...}
```

---

## Modelle

| Alias (external) | Echter Ollama-Name | Zweck |
|---|---|---|
| `qwen3.6` | qwen3.6:35b-a3b-q4_K_M | General-Chat, schnell (kein Thinking) |
| `qwen3.6-think` | qwen3.6:35b-a3b-q4_K_M | Gleiches Modell, mit sichtbarem Reasoning (langsamer) |
| `qwen3-coder` | qwen3-coder:30b | Coding (optimiert fuer Code) |
| `nomic-embed` | nomic-embed-text | Embeddings (Vector-Search, RAG) |

Aliase in `litellm_config.yaml`. Neue Modelle:

```yaml
model_list:
  - model_name: <kurz-name>
    litellm_params:
      model: ollama/<echter-name>
      api_base: http://host.docker.internal:11434
```

Dann `docker compose restart litellm`.

### Capabilities (was koennen die Modelle?)

LiteLLM meldet pro Modell Fähigkeiten via `/model/info`. Clients wie Chatbox, Continue oder Zed lesen das aus und aktivieren z. B. den Foto-Upload-Button nur bei Vision-fähigen Modellen.

| Alias | Vision (Bilder) | Function-Calling | Thinking/Reasoning | Max Input |
|---|---|---|---|---|
| `qwen3.6` | ✓ | ✓ | — (aus) | 32k |
| `qwen3.6-think` | ✓ | ✓ | ✓ (sichtbar) | 32k |
| `qwen3-coder` | — | ✓ | — | 32k |
| `nomic-embed` | — | — | — | 8k |

**Bilder:** Kamerafoto oder Screenshot wird als base64 im Message-Content mitgeschickt — funktioniert mit `qwen3.6`/`qwen3.6-think` (Ollama-Capability `vision` ist aktiv).

**PDFs:** Im OpenAI-Schema gibt es dafuer kein eigenes Flag. In der Praxis:
- Die meisten Clients (Chatbox, Continue, Zed) extrahieren Text **clientseitig** und schicken ihn als Text-Nachricht → funktioniert mit jedem Modell, nichts zu konfigurieren.
- Manche Clients rendern PDF-Seiten zu Bildern → greift auf `supports_vision` zurueck, also auch abgedeckt.

Capabilities werden in `litellm_config.yaml` pro Modell unter `model_info:` gesetzt (`supports_vision`, `supports_function_calling`, `supports_reasoning`, `max_input_tokens`, …). Verifikation:

```bash
curl -s -H "Authorization: Bearer $MASTER_KEY" http://127.0.0.1:4000/model/info | jq '.data[] | {name:.model_name, vision:.model_info.supports_vision, func:.model_info.supports_function_calling}'
```

---

## API-Keys verwalten

### Via Admin-UI (empfohlen)

1. Im Browser im LAN: **http://192.168.1.155:4001**
2. Status pruefen (sollte "✓ OK" zeigen)
3. **Neuer Key** Form:
   - Name: z.B. "Continue @ Laptop"
   - Modelle auswaehlen (Default: alle)
   - Requests/min: 60 ist gut als Start
   - Laufzeit: leer (unbegrenzt) oder z.B. `30d`
4. Key-Klartext **einmalig** kopieren
5. In Tool-Config einsetzen
6. Key widerrufen: Liste unten, "widerrufen"-Button

### Via curl (Alternative)

```bash
MASTER=$(grep MASTER_KEY /home/sember/rose-litellm/.env | cut -d= -f2)

# Key erstellen
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{"key_alias":"MyTool","models":["qwen3-coder","nomic-embed"],"rpm_limit":60}'

# Key widerrufen
curl -X POST http://localhost:4000/key/delete \
  -H "Authorization: Bearer $MASTER" \
  -H "Content-Type: application/json" \
  -d '{"keys":["sk-..."]}'
```

### Persistenz

Keys + Spend liegen in `rose-litellm-db` (Postgres-Volume `litellm_pgdata`).
Container-Neustart = Keys bleiben.

---


## URL-Konvention in verschiedenen Tools

Der gleiche Endpoint, aber Tools unterscheiden sich wie sie die Base-URL erwarten:

| Tool | Base-URL-Feld |
|---|---|
| OpenAI Python SDK, Continue.dev, Aider, Zed, Cursor | `https://www.sember.de/llm/v1`  (mit /v1) |
| Chatbox, manche iOS-Apps | `https://www.sember.de/llm`  (ohne /v1) |
| curl (komplette URL selbst) | `https://www.sember.de/llm/v1/chat/completions` |

**Standard ist mit /v1** (OpenAI-Convention). Wenn ein Tool Model-Auto-Discovery
fehlschlagen laesst, erst die URL OHNE /v1 probieren — das Tool haengt dann selbst `/v1/*` an.

## Tool-Configs

### Continue.dev (`~/.continue/config.json`)

```json
{
  "models": [
    {
      "title": "Qwen3-Coder @ Rose",
      "provider": "openai",
      "model": "qwen3-coder",
      "apiBase": "https://www.sember.de/llm/v1",
      "apiKey": "sk-rose-..."
    },
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

### Aider (CLI)

```bash
aider \
  --openai-api-base https://www.sember.de/llm/v1 \
  --openai-api-key sk-rose-... \
  --model openai/qwen3-coder
```

Oder in `~/.aider.conf.yml`:
```yaml
openai-api-base: https://www.sember.de/llm/v1
openai-api-key: sk-rose-...
model: openai/qwen3-coder
```

### Zed (`settings.json`)

```json
{
  "assistant": {
    "default_model": {
      "provider": "openai_compatible",
      "api_url": "https://www.sember.de/llm/v1",
      "api_key_env": "ROSE_API_KEY",
      "available_models": [
        { "name": "qwen3.6", "display_name": "Qwen 3.6", "max_tokens": 16384 },
        { "name": "qwen3-coder", "display_name": "Qwen3 Coder", "max_tokens": 16384 }
      ]
    }
  }
}
```
Plus Umgebungsvariable setzen: `export ROSE_API_KEY=sk-rose-...`

### Cursor (Settings → Models)

- "Override OpenAI Base URL": `https://www.sember.de/llm/v1`
- "OpenAI API Key": `sk-rose-...`
- Im Chat: Modell auswaehlen aus Dropdown

### Cline (VS Code)

- Provider: "OpenAI Compatible"
- Base URL: `https://www.sember.de/llm/v1`
- API Key: `sk-rose-...`
- Model ID: `qwen3-coder` (manuell eingeben)

### Python Skript

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://www.sember.de/llm/v1",
    api_key="sk-rose-..."
)

resp = client.chat.completions.create(
    model="qwen3-coder",
    messages=[{"role": "user", "content": "Fibonacci in Python"}]
)
print(resp.choices[0].message.content)
```

---

## Testen

### Schnelltest (3 curl-Calls)

```bash
KEY=sk-rose-...

# 1. Health
curl https://www.sember.de/llm/v1/models \
  -H "Authorization: Bearer $KEY"
# -> Liste mit 3 Modellen

# 2. Chat
curl -X POST https://www.sember.de/llm/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.6","messages":[{"role":"user","content":"Sag Hallo"}]}'

# 3. Embedding
curl -X POST https://www.sember.de/llm/v1/embeddings \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed","input":"Beispieltext"}'
```

Alle drei → HTTP 200 mit JSON-Antwort = alles in Ordnung.

### End-to-End-Test mit Continue.dev (empfohlen)

1. VS Code + Continue-Extension installieren
2. `config.json` wie oben eintragen (Key vorher in Admin-UI erstellt)
3. Continue-Chat oeffnen, Modell waehlen, "Hallo" schicken
4. Sollte nach 1-3s antworten
5. Codedatei oeffnen, Zeilen markieren, "Erklaere diesen Code"
6. Rose-Modell erklaert den Code

### Troubleshooting

| Symptom | Ursache | Fix |
|---|---|---|
| `401 Unauthorized` | Key falsch/widerrufen/abgelaufen | In Admin-UI neuen Key erstellen |
| `404 Not Found` auf `/llm/v1/...` | Caddy-Config nicht geladen | `sudo systemctl reload caddy` |
| `502 Bad Gateway` | LiteLLM-Container down | `docker logs rose-litellm` pruefen |
| `model not found` | Alias-Name falsch | Liste per `/v1/models` pruefen |
| Langsam / Timeouts | Modell nicht im Ollama-RAM | erstmalige Anfrage laedt (30-60s), dann flott |
| `429 Rate Limit` | rpm_limit ueberschritten | In Admin-UI Key editieren oder warten |

### Logs

```bash
# LiteLLM
docker logs rose-litellm --tail 50

# Admin-UI
docker logs rose-litellm-admin --tail 50

# Caddy Access-Log (enthaelt /llm-Requests)
sudo tail -f /var/log/caddy/access.log | grep '/llm/'

# Postgres
docker logs rose-litellm-db --tail 50
```

---


## Performance-Tipps

### Thinking-Modus

qwen3.6 hat einen internen Denken-Modus. Default in Ollama: **an**, was bei
kurzen Fragen 5-10 Sekunden Wartezeit bedeutet (das Modell generiert interne
Thinking-Tokens bevor die Antwort kommt).

Die  setzt  per default fuer qwen3.6 — dadurch
antworten simple Fragen in 200-400ms statt 5-10s.

Falls ein Client Thinking explizit will, kann er im Request-Body
 setzen und LiteLLMs Default wird ueberschrieben.

qwen3-coder hat kein Thinking, wird deshalb nicht manipuliert.

### Erste Request nach Pause

Ollama evictet geladene Modelle nach  (Spark default:
-1 = nie). Falls doch mal ein Modell neu geladen werden muss: 30-90s
Wartezeit beim ersten Request, danach flott.

## Wartung

### Update der LiteLLM-Version

```bash
cd /home/sember/rose-litellm
docker compose pull litellm
docker compose up -d litellm
```

Prisma fuehrt bei Start eventuelle DB-Migrations automatisch durch.

### Modelle hinzufuegen / entfernen

```bash
# Ollama-seitig
ollama pull <neues-modell>

# LiteLLM-Alias ergaenzen
vim /home/sember/rose-litellm/litellm_config.yaml
docker compose restart litellm
```

### Backup

**Kritisch:** `/var/lib/docker/volumes/rose-litellm_litellm_pgdata/`

```bash
# Dump
docker exec rose-litellm-db pg_dump -U litellm litellm > litellm-backup-$(date +%Y%m%d).sql

# Restore
cat litellm-backup-YYYYMMDD.sql | docker exec -i rose-litellm-db psql -U litellm -d litellm
```

Verlust = alle User-Keys weg, muessen neu erstellt werden.
Der Master-Key (in `.env`) ist stateless und ueberlebt immer.

### Spend-Monitoring

Aktuelle Spend-Daten pro Key aus der Postgres-Tabelle:
```sql
SELECT key_alias, spend, rpm_limit FROM "LiteLLM_VerificationToken"
ORDER BY spend DESC;
```

Ollama selbst kostet nichts — der `spend`-Wert ist fiktiv (LiteLLM rechnet mit
internen Preisen), aber nuetzlich als Request-Zaehler.

---

## Sicherheit

### Was geschuetzt ist

- **Port 11434 (Ollama)** bleibt extern **geschlossen** (UFW)
- **Port 4000 (LiteLLM)** nur auf localhost gebunden
- **Port 4001 (Admin)** nur auf LAN-IP `192.168.1.155` gebunden — aus Internet **nicht erreichbar**
- **Master-Key** nur in `.env` (Rechte 600) + Container-Env — niemals im Frontend
- **TLS** automatisch via Let's Encrypt (Caddy) fuer www.sember.de
- **API-Keys** bcrypt-gehasht in der DB (LiteLLM-interne Implementierung)

### Best Practices

1. Dedizierten Key pro Tool erstellen (leichter widerruflich bei Leak)
2. `rpm_limit` setzen pro Key (60-120 fuer Chat reicht)
3. `models` pro Key scopen (Coder-Tool nur `qwen3-coder`, nicht alle)
4. `duration: "90d"` fuer Dritt-User (Ablauf erzwingt regelmaessige Rotation)
5. Bei Leak: in Admin-UI sofort widerrufen
6. LiteLLM und Admin regelmaessig updaten (Security-Patches)

### Logging

- **Caddy-Access-Log:** enthaelt `/llm/*`-URLs, Status-Codes, Client-IPs
  - **Keine** Request-Bodies (ist Caddy-Standard)
- **LiteLLM:** Requests loggen mit Modell, Tokens, Latency — **keine Prompt-Inhalte**
- **Admin:** keine persistente Logs (FastAPI-Stdout fuer Debugging)

Fuer vollen Audit-Trail kann `LiteLLM_AuditLog` in der DB aktiviert werden — default aus.

---

## Was wenn was kaputt geht

### LiteLLM startet nicht

```bash
docker logs rose-litellm 2>&1 | tail -50
```

Haeufige Ursachen:
- `DATABASE_URL` falsch (typo in `.env`)
- Postgres nicht healthy — `docker logs rose-litellm-db`
- `litellm_config.yaml` Syntax-Fehler — `docker compose config`

### Admin-UI zeigt "Admin kann LiteLLM nicht erreichen"

```bash
docker exec rose-litellm-admin wget -qO- http://litellm:4000/health/readiness
```

Wenn das fehlschlaegt: LiteLLM laeuft nicht oder docker-Netzwerk broken.

### Alles platt — Clean-Reset

```bash
cd /home/sember/rose-litellm
docker compose down
docker compose up -d
```

Postgres-Volume bleibt erhalten (Keys persistent).

### Wirklich alles loeschen

```bash
cd /home/sember/rose-litellm
docker compose down -v   # -v loescht auch das Postgres-Volume!
```

Danach alle Keys weg, saubere Neu-Installation.

---

## Erweiterungen (falls irgendwann gewuenscht)

- **TTL-Cleanup** alter Keys via Cron
- **IP-Whitelist** pro Key (LiteLLM unterstuetzt `allowed_ips`)
- **Budget** pro Key (`max_budget: 10.0` — in USD-fiktiv)
- **Email-Report** wochenweise aus den `LiteLLM_Daily*Spend`-Tabellen
- **Cloudflare-Tunnel** statt offenem Port 443 (extra DDoS-Schutz)
- **Zweite Subdomain `llm.sember.de`** falls Pfadgebundenheit stoert

Das war's. Viel Spass mit dem Gateway.
