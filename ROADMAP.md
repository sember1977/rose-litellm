# Roadmap

## Legende
- `[ ]` — offen
- `[~]` — in Arbeit
- `[x]` — erledigt (Version in Klammern)

---

## Backlog

- [ ] TTL-Cleanup alter Keys via Cron
- [ ] IP-Whitelist pro Key (LiteLLM `allowed_ips`)
- [ ] Email-Report wöchentlich aus Spend-Tabellen
- [ ] Cloudflare-Tunnel statt offenem Port 443

---

## Abgeschlossen

- [x] LiteLLM Proxy mit Multi-Model-Routing (0.7.0)
- [x] Postgres-Backend + Key-Persistenz (0.7.0)
- [x] Admin-UI: Key-Verwaltung + Status (0.7.0)
- [x] Dashboard: Nutzung heute + Aktivitäts-Indikator (0.7.1)
- [x] Dashboard: Request-Verlauf als Chart (24h) (0.7.2)
- [x] Dashboard: Filtermöglichkeit nach Key-Alias (0.7.2)
- [x] Per-Key Prompt-Logging (Admin-Tab Prompt-Logs) (0.8.0)
- [x] Modell-Landschaft bereinigt: qwen-chemicals / llama405B-Chemicals / ionos-llama405b / chemicals-ionos / qwen2.5-vl-Alias entfernt (Config + Key-Allowlists + DB) (0.9.0)

---

Stand: 0.9.0
