# Changelog

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
