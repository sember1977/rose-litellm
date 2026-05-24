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
        return {"models": [], "total_requests": 0, "error": str(e)[:200]}

    models = []
    total_requests = 0
    for r in rows:
        model, reqs, pt, ct, spend, last_req, active = r
        total_requests += reqs
        models.append({
            "model": model,
            "requests": reqs,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "spend": round(spend, 6),
            "last_request_at": last_req.isoformat() if last_req else None,
            "active_last_10min": bool(active),
        })
    return {"models": models, "total_requests": total_requests}


@app.get("/api/dashboard/recent")
def dashboard_recent():
    """Letzte 20 Requests aus LiteLLM_SpendLogs."""
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT sl."request_id", sl.model, vt.key_alias,
                   sl.prompt_tokens, sl.completion_tokens, sl.spend,
                   sl.status, sl."startTime",
                   EXTRACT(EPOCH FROM (sl."endTime" - sl."startTime")) * 1000 AS duration_ms
            FROM "LiteLLM_SpendLogs" sl
            LEFT JOIN "LiteLLM_VerificationToken" vt ON sl.api_key = vt.token
            ORDER BY sl."startTime" DESC
            LIMIT 20
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
