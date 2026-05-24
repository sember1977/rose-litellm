# Changelog

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
