# Changelog

## 0.8.0 — Per-Key Prompt-Logging (Admin-Tab Prompt-Logs)

**Warum:** SpendLogs zeigen nur Metadaten (Tokens, Kosten, Status). Um zu sehen
*welche* Prompts ein bestimmter Key tatsaechlich stellt — z.B. um ein neues
Kollegen-Setup zu pruefen oder einen Bug nachzuvollziehen — fehlt ein Plaintext-
Log. Globales Prompt-Logging waere datenschutz- und ressourcen-teuer. Loesung:
genau ein Key zur Zeit, opt-in, ueber Web-UI ein-/ausschaltbar.

**Geaendert:**
- `litellm_config.yaml`: `callbacks: custom_loggers.active_key_logger.active_key_logger_instance`
- `docker-compose.yml`: neues Volume `litellm-logs` (shared zwischen `rose-litellm`
  und `rose-litellm-admin`), `custom_loggers/`-Mount im litellm-Container,
  `KEY_LOG_ROOT=/data` + `PYTHONPATH=/app:/app/custom_loggers`.
- `admin/app.py`: neue Endpoints `/api/logs/active` (GET/POST), `/api/logs/list`,
  `/api/logs/stream` (SSE Live-Feed), Route `/logs`.
- `admin/static/index.html` + `dashboard.html`: Nav-Tab "Prompt-Logs".

**Neu:**
- `custom_loggers/active_key_logger.py`: LiteLLM-CustomLogger, liest `/data/active_key.txt`
  bei jedem Call. Leerer Inhalt = Logging aus. Nur Calls deren `user_api_key_alias`
  matched landen in `/data/logs/{alias}-{YYYY-MM-DD}.jsonl` (Tagesrotation, UTC).
- `admin/static/logs.html` + `logs.js`: Dropdown zur Key-Auswahl, Status-Pill
  Aktiv/Aus, Live-Feed-Tabelle (Zeit/Modell/IP/Prompt-Excerpt/Response-Excerpt/
  Tokens/Dauer), Detail-Modal pro Eintrag mit vollem Messages-Array.

**Sicherheit/Datenschutz:**
- Default = aus. Logging ist explizit opt-in pro Key.
- Logs liegen plaintext auf dem Spark in `/var/lib/docker/volumes/rose-litellm_litellm-logs/_data/logs/`.
- Admin-UI ist nur LAN-erreichbar (192.168.1.155:4001) — keine externe Exposition.
- Andere Keys werden vom Logger bereits am ersten File-Read-Vergleich verworfen
  (~1 ms Overhead pro Call wenn aus, sonst ~5 ms).

## 0.7.2 — Dashboard: Chart + Filter

**Warum:** Ohne zeitlichen Verlauf und Key-Filter ist das Dashboard nur eine
Momentaufnahme. Der 24h-Chart zeigt Lastspitzen und Nutzungsmuster auf einen
Blick. Der Key-Filter erlaubt, die Requests eines bestimmten Nutzers/Tools
isoliert zu betrachten.

**Geändert:**
- `admin/app.py`: Neue Endpoints `/api/dashboard/timeline` (24h-Buckets pro Modell)
  und `/api/dashboard/key-aliases` (alle bekannten Aliase). `/api/dashboard/recent`
  akzeptiert `?key_alias=` und limitiert auf 50 (vorher 20). `/api/dashboard/today`
  liefert jetzt `total_spend`.
- `admin/static/dashboard.html`: Neue Chart-Card (Canvas), Key-Filter-Dropdown,
  Fusszeile in Heute-Tabelle mit Summen (Requests, Tokens, Kosten).
- `admin/static/dashboard.js`: Canvas-Bar-Chart (gestapelt, 24 Balken, Tooltips,
  Legende), Filter-Logik (Chart+Tabelle aktualisieren sich bei Dropdown-Wechsel),
  Summenzeilen-Berechnung, Timeline-Refresh alle 2 Min.
- `admin/static/style.css`: Styles fuer Chart-Container, Legende, Filter-Row,
  Table-Footer.

## 0.7.1 — Dashboard-Seite

**Warum:** Ohne Sichtbarkeit der Nutzung ist unklar, ob/wie stark die Modelle
genutzt werden und ob der Service läuft. Das Dashboard schließt diese Lücke mit
Live-Daten aus der vorhandenen `LiteLLM_SpendLogs`-Tabelle.

**Geändert:**
- `admin/app.py`: Drei neue API-Endpunkte (`/api/dashboard/today`, `/recent`, `/health`)
  plus `/dashboard`-Route für die neue HTML-Seite.
- `admin/static/index.html`: Tab-Navigation zwischen Keys-UI und Dashboard.
- `admin/static/style.css`: Styles für Tabs und Dashboard-Tabellen.

**Neu:**
- `admin/static/dashboard.html`: Dashboard-UI — Tabelle "Heute pro Modell" +
  Liste "Letzte 20 Requests".
- `admin/static/dashboard.js`: Rendert Nutzungsdaten, pollt alle 30s
  Aktivitätsstatus, alle 60s komplette Daten.

## 0.7.0 — Initial deploy

- LiteLLM Proxy mit 14 Modellen (lokal Qwen3/Embed, Cloud Gemini/DeepSeek/IONOS)
- Postgres-Backend fuer Keys und Spend-Tracking
- Admin-UI (LAN-only) fuer Key-Verwaltung + Status
- Caddy Reverse-Proxy unter www.sember.de/llm/
