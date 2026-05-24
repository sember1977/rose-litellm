"""Rose LiteLLM Admin — lokale UI zur Key-Verwaltung + Status + Dashboard.

NUR LAN-ZUGRIFF (Port 4001 an LAN-IP gebunden).

Keys werden direkt aus der LiteLLM-DB gelesen (LiteLLM_VerificationToken).
Create/Delete laufen ueber LiteLLMs REST-API.
Dashboard aggregiert SpendLogs aus der gleichen DB.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
LAN_HOST = os.environ.get("LAN_HOST", "http://192.168.1.155")

app = FastAPI(title="Rose LiteLLM Admin")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _headers() -> dict:
    if not MASTER_KEY:
        raise HTTPException(500, "Master-Key nicht konfiguriert")
    return {"Authorization": f"Bearer {MASTER_KEY}"}


def _db():
    if not DATABASE_URL:
        raise HTTPException(500, "DATABASE_URL nicht konfiguriert")
    return psycopg2.connect(DATABASE_URL)


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/api/status")
async def status():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            h = await client.get(f"{LITELLM_URL}/health/readiness")
            m = await client.get(f"{LITELLM_URL}/v1/models", headers=_headers())
        except httpx.HTTPError as e:
            return JSONResponse(
                {"healthy": False, "error": str(e), "models": []},
                status_code=200,
            )
    models = [x["id"] for x in (m.json().get("data", []) if m.status_code == 200 else [])]
    return {
        "healthy": h.status_code == 200,
        "litellm_version": h.json().get("litellm_version") if h.status_code == 200 else None,
        "db": h.json().get("db") if h.status_code == 200 else "unknown",
        "models": models,
        "api_base_external": "https://www.sember.de/llm/v1",
        "lan_host": LAN_HOST,
    }


@app.get("/api/keys")
def list_keys():
    """Direkt aus der LiteLLM-DB gelesen."""
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT token, key_alias, models, rpm_limit, tpm_limit, spend,
                   max_budget, expires, created_at
            FROM "LiteLLM_VerificationToken"
            WHERE key_alias IS NOT NULL
            ORDER BY created_at DESC NULLS LAST
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"keys": [], "error": str(e)[:200]}

    keys = []
    for r in rows:
        token, alias, models, rpm, tpm, spend, budget, expires, created = r
        keys.append({
            "token": token,
            "token_prefix": (token[:16] + "...") if token else "—",
            "alias": alias or "—",
            "models": list(models) if models else [],
            "rpm_limit": rpm,
            "tpm_limit": tpm,
            "spend": float(spend) if spend is not None else 0.0,
            "max_budget": float(budget) if budget is not None else None,
            "expires": expires.isoformat() if expires else None,
            "created_at": created.isoformat() if created else None,
        })
    return {"keys": keys}


@app.post("/api/keys")
async def create_key(body: dict):
    payload = {
        "key_alias": (body.get("alias") or "unnamed").strip()[:64],
    }
    if body.get("models"):
        payload["models"] = body["models"]
    if body.get("rpm_limit"):
        payload["rpm_limit"] = int(body["rpm_limit"])
    if body.get("duration"):
        payload["duration"] = body["duration"]

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                f"{LITELLM_URL}/key/generate",
                headers=_headers(),
                json=payload,
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"litellm_unreachable: {e}")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])
    return r.json()


@app.post("/api/keys/delete")
async def delete_key(body: dict):
    key = body.get("key", "").strip()
    if not key:
        raise HTTPException(400, "key fehlt")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(
                f"{LITELLM_URL}/key/delete",
                headers=_headers(),
                json={"keys": [key]},
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"litellm_unreachable: {e}")
    return {"status_code": r.status_code, "body": r.text[:200]}


# ─── Dashboard ────────────────────────────────────────────────────

@app.get("/api/dashboard/today")
def dashboard_today():
    """Heutige Nutzung aggregiert pro Modell aus LiteLLM_SpendLogs."""
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT model,
                   COUNT(*)::int AS requests,
                   COALESCE(SUM(prompt_tokens), 0)::bigint AS prompt_tokens,
                   COALESCE(SUM(completion_tokens), 0)::bigint AS completion_tokens,
                   COALESCE(SUM(spend), 0)::float AS spend,
                   MAX("startTime") AS last_request_at,
                   BOOL_OR("startTime" > NOW() - INTERVAL '10 minutes') AS active_last_10min
            FROM "LiteLLM_SpendLogs"
            WHERE "startTime" >= CURRENT_DATE
            GROUP BY model
            ORDER BY requests DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"models": [], "total_requests": 0, "total_spend": 0.0, "error": str(e)[:200]}

    models = []
    total_requests = 0
    total_spend = 0.0
    for r in rows:
        model, reqs, pt, ct, spend, last_req, active = r
        total_requests += reqs
        total_spend += spend
        models.append({
            "model": model,
            "requests": reqs,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "spend": round(spend, 6),
            "last_request_at": last_req.isoformat() if last_req else None,
            "active_last_10min": bool(active),
        })
    return {"models": models, "total_requests": total_requests, "total_spend": round(total_spend, 6)}


@app.get("/api/dashboard/recent")
def dashboard_recent(key_alias: str | None = None):
    """Letzte 50 Requests aus LiteLLM_SpendLogs. Optional nach key_alias filterbar."""
    try:
        conn = _db()
        cur = conn.cursor()
        if key_alias:
            cur.execute("""
                SELECT sl."request_id", sl.model, vt.key_alias,
                       sl.prompt_tokens, sl.completion_tokens, sl.spend,
                       sl.status, sl."startTime",
                       EXTRACT(EPOCH FROM (sl."endTime" - sl."startTime")) * 1000 AS duration_ms
                FROM "LiteLLM_SpendLogs" sl
                LEFT JOIN "LiteLLM_VerificationToken" vt ON sl.api_key = vt.token
                WHERE vt.key_alias = %s
                ORDER BY sl."startTime" DESC
                LIMIT 50
            """, (key_alias,))
        else:
            cur.execute("""
                SELECT sl."request_id", sl.model, vt.key_alias,
                       sl.prompt_tokens, sl.completion_tokens, sl.spend,
                       sl.status, sl."startTime",
                       EXTRACT(EPOCH FROM (sl."endTime" - sl."startTime")) * 1000 AS duration_ms
                FROM "LiteLLM_SpendLogs" sl
                LEFT JOIN "LiteLLM_VerificationToken" vt ON sl.api_key = vt.token
                ORDER BY sl."startTime" DESC
                LIMIT 50
            """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"requests": [], "error": str(e)[:200]}

    requests = []
    for r in rows:
        rid, model, alias, pt, ct, spend, status, start, dur = r
        requests.append({
            "request_id": rid,
            "model": model,
            "key_alias": alias or "—",
            "prompt_tokens": pt or 0,
            "completion_tokens": ct or 0,
            "spend": round(float(spend), 6) if spend else 0,
            "status": status or "unknown",
            "startTime": start.isoformat() if start else None,
            "duration_ms": round(float(dur)) if dur else None,
        })
    return {"requests": requests}


@app.get("/api/dashboard/health")
def dashboard_health():
    """Schnell-Check: welche Modelle hatten in den letzten 10 Min Traffic."""
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT model, COUNT(*)::int AS requests,
                   MAX("startTime") AS last_request_at
            FROM "LiteLLM_SpendLogs"
            WHERE "startTime" > NOW() - INTERVAL '10 minutes'
            GROUP BY model
            ORDER BY requests DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"active_models": [], "error": str(e)[:200]}

    active_models = []
    for r in rows:
        model, reqs, last_req = r
        active_models.append({
            "model": model,
            "requests": reqs,
            "last_request_at": last_req.isoformat() if last_req else None,
        })
    return {"active_models": active_models}


@app.get("/api/dashboard/timeline")
def dashboard_timeline(key_alias: str | None = None):
    """Request-Counts pro Stunde der letzten 24h, gruppiert nach Modell.

    Optional nach key_alias filterbar — dann zaehlen nur Requests dieses Keys.
    """
    try:
        conn = _db()
        cur = conn.cursor()
        if key_alias:
            cur.execute("""
                SELECT date_trunc('hour', sl."startTime") AS hour,
                       sl.model,
                       COUNT(*)::int AS requests
                FROM "LiteLLM_SpendLogs" sl
                JOIN "LiteLLM_VerificationToken" vt ON sl.api_key = vt.token
                WHERE sl."startTime" >= NOW() - INTERVAL '24 hours'
                  AND vt.key_alias = %s
                GROUP BY hour, sl.model
                ORDER BY hour
            """, (key_alias,))
        else:
            cur.execute("""
                SELECT date_trunc('hour', sl."startTime") AS hour,
                       sl.model,
                       COUNT(*)::int AS requests
                FROM "LiteLLM_SpendLogs" sl
                WHERE sl."startTime" >= NOW() - INTERVAL '24 hours'
                GROUP BY hour, sl.model
                ORDER BY hour
            """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"buckets": [], "models": [], "error": str(e)[:200]}

    buckets = []
    model_set = set()
    for r in rows:
        hour, model, reqs = r
        model_set.add(model)
        buckets.append({
            "hour": hour.isoformat() if hour else None,
            "model": model,
            "requests": reqs,
        })
    return {"buckets": buckets, "models": sorted(model_set)}


@app.get("/api/dashboard/key-aliases")
def dashboard_key_aliases():
    """Alle bekannten Key-Aliase aus SpendLogs + VerificationToken."""
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT COALESCE(vt.key_alias, 'unbekannt') AS alias
            FROM "LiteLLM_SpendLogs" sl
            LEFT JOIN "LiteLLM_VerificationToken" vt ON sl.api_key = vt.token
            ORDER BY alias
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"aliases": [], "error": str(e)[:200]}

    return {"aliases": [r[0] for r in rows]}
# ─── Prompt-Logs (Per-Key Live-Feed) ─────────────────────────────
# Aktiver Alias steht in /data/active_key.txt (shared volume mit rose-litellm-Container).
# JSONL-Tageslogs in /data/logs/{alias}-{YYYY-MM-DD}.jsonl.

import asyncio
import json as _json
from datetime import datetime, timezone, timedelta
from fastapi import Request
from fastapi.responses import StreamingResponse

LOGS_ROOT = Path(os.environ.get("KEY_LOG_ROOT", "/data"))
LOGS_ACTIVE_FILE = LOGS_ROOT / "active_key.txt"
LOGS_DIR = LOGS_ROOT / "logs"


def _logs_safe_alias(alias: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in alias) or "unknown"


def _logs_read_active() -> str:
    try:
        return LOGS_ACTIVE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _logs_write_active(alias: str) -> None:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    LOGS_ACTIVE_FILE.write_text(alias or "", encoding="utf-8")


def _logs_files_for(alias: str, days: int = 2) -> list[Path]:
    """Heutige + (days-1) vorherige Dateien fuer den Alias, neueste zuerst."""
    if not alias:
        return []
    safe = _logs_safe_alias(alias)
    out: list[Path] = []
    today = datetime.now(timezone.utc).date()
    for i in range(days):
        d = today - timedelta(days=i)
        p = LOGS_DIR / f"{safe}-{d.isoformat()}.jsonl"
        if p.exists():
            out.append(p)
    return out


def _logs_read_lines(alias: str, limit: int = 100) -> list[dict]:
    """Liest die letzten N Eintraege fuer den Alias (heutige + gestrige Datei)."""
    files = _logs_files_for(alias, days=2)
    entries: list[dict] = []
    for p in files:
        try:
            with p.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(_json.loads(line))
                    except Exception:
                        continue
        except Exception:
            continue
    # Neueste zuerst
    entries.reverse()
    return entries[:limit]


@app.get("/logs", include_in_schema=False)
def logs_page():
    return FileResponse(STATIC_DIR / "logs.html")


@app.get("/api/logs/active")
def logs_get_active():
    alias = _logs_read_active()
    safe = _logs_safe_alias(alias) if alias else ""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "alias": alias,
        "logfile": f"{safe}-{today}.jsonl" if alias else None,
    }


@app.post("/api/logs/active")
def logs_set_active(body: dict):
    alias = (body.get("alias") or "").strip()
    # Optional: pruefen ob der Alias bei LiteLLM bekannt ist — wir verzichten,
    # damit ein Stopp (leerer String) immer durchgeht.
    _logs_write_active(alias)
    return {"ok": True, "alias": alias}


@app.get("/api/logs/list")
def logs_list(limit: int = 50):
    alias = _logs_read_active()
    if not alias:
        return {"alias": "", "entries": []}
    if limit < 1 or limit > 500:
        limit = 50
    return {"alias": alias, "entries": _logs_read_lines(alias, limit=limit)}


@app.get("/api/logs/stream")
async def logs_stream(request: Request):
    """SSE — pollt mtime der heutigen Datei, streamt neue Zeilen + Aktiv-Wechsel."""
    async def event_gen():
        last_alias = _logs_read_active()
        last_size = 0
        last_path: Path | None = None

        def _today_path(alias: str) -> Path | None:
            if not alias:
                return None
            safe = _logs_safe_alias(alias)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return LOGS_DIR / f"{safe}-{today}.jsonl"

        # Init
        last_path = _today_path(last_alias)
        if last_path and last_path.exists():
            last_size = last_path.stat().st_size

        # Initial status push
        yield f"event: active\ndata: {_json.dumps({'alias': last_alias})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            current_alias = _logs_read_active()
            if current_alias != last_alias:
                last_alias = current_alias
                last_path = _today_path(last_alias)
                last_size = last_path.stat().st_size if (last_path and last_path.exists()) else 0
                yield f"event: active\ndata: {_json.dumps({'alias': last_alias})}\n\n"

            # Logging aus? Nur Heartbeat
            if not last_alias or not last_path:
                yield ": ping\n\n"
                await asyncio.sleep(2.0)
                continue

            # Datei evtl. neu (Tageswechsel)
            if not last_path.exists():
                last_path = _today_path(last_alias)
                last_size = 0
                if not last_path or not last_path.exists():
                    yield ": ping\n\n"
                    await asyncio.sleep(2.0)
                    continue

            try:
                cur_size = last_path.stat().st_size
            except FileNotFoundError:
                last_size = 0
                yield ": ping\n\n"
                await asyncio.sleep(2.0)
                continue

            if cur_size > last_size:
                try:
                    with last_path.open("r", encoding="utf-8") as fh:
                        fh.seek(last_size)
                        new_text = fh.read()
                        last_size = fh.tell()
                except Exception:
                    new_text = ""
                for line in new_text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = _json.loads(line)
                    except Exception:
                        continue
                    yield f"event: entry\ndata: {_json.dumps(obj, default=str)}\n\n"
            elif cur_size < last_size:
                # Datei wurde rotiert/getrimmt — reset
                last_size = 0
            else:
                yield ": ping\n\n"

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
