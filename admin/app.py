"""Rose LiteLLM Admin — kleine lokale UI zur Key-Verwaltung + Status.

NUR LAN-ZUGRIFF (Port 4001 an LAN-IP gebunden).

Keys werden direkt aus der LiteLLM-DB gelesen (LiteLLM_VerificationToken).
Create/Delete laufen ueber LiteLLMs REST-API.
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
