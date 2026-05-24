"""Active-Key-Logger fuer LiteLLM.

Loggt Prompts+Responses NUR fuer genau einen Key-Alias zur Zeit. Der aktive
Alias steht in /data/active_key.txt (geschrieben von rose-litellm-admin).
Leerer Datei-Inhalt oder fehlende Datei = Logging vollstaendig aus.

JSONL-Output landet in /data/logs/{alias}-{YYYY-MM-DD}.jsonl (UTC-Tage).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from litellm.integrations.custom_logger import CustomLogger

ROOT = Path(os.environ.get("KEY_LOG_ROOT", "/data"))
ACTIVE_FILE = ROOT / "active_key.txt"
LOG_DIR = ROOT / "logs"


def _read_active() -> str:
    """Aktuell zu loggender Alias. Bei jedem Call frisch gelesen — File ist winzig."""
    try:
        return ACTIVE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _logfile_for(alias: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in alias) or "unknown"
    return LOG_DIR / f"{safe}-{today}.jsonl"


def _write(alias: str, entry: dict) -> None:
    path = _logfile_for(alias)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=str))
        fh.write("\n")


def _extract_alias(kwargs: dict) -> str:
    meta = (kwargs.get("litellm_params") or {}).get("metadata") or {}
    return (
        meta.get("user_api_key_alias")
        or kwargs.get("user_api_key_alias")
        or ""
    )


def _extract_response_text(response_obj) -> str:
    try:
        if hasattr(response_obj, "choices") and response_obj.choices:
            choice = response_obj.choices[0]
            msg = getattr(choice, "message", None)
            if msg is not None:
                return getattr(msg, "content", "") or ""
            # Streaming-Delta-Fall (selten beim success-event):
            delta = getattr(choice, "delta", None)
            if delta is not None:
                return getattr(delta, "content", "") or ""
    except Exception:
        pass
    return ""


def _extract_usage(response_obj) -> dict | None:
    usage = getattr(response_obj, "usage", None)
    if usage is None:
        return None
    try:
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
    except Exception:
        return None


def _extract_ip(kwargs: dict) -> str | None:
    meta = (kwargs.get("litellm_params") or {}).get("metadata") or {}
    return meta.get("requester_ip_address") or meta.get("user_ip") or None


def _build_entry(kwargs: dict, response_obj, start_time, end_time, alias: str) -> dict:
    duration_ms = None
    try:
        if start_time and end_time:
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
    except Exception:
        duration_ms = None
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "alias": alias,
        "model": kwargs.get("model"),
        "messages": kwargs.get("messages") or kwargs.get("input") or [],
        "response": _extract_response_text(response_obj),
        "usage": _extract_usage(response_obj),
        "ip": _extract_ip(kwargs),
        "duration_ms": duration_ms,
    }


class ActiveKeyLogger(CustomLogger):
    """LiteLLM-CustomLogger — filtert auf den per active_key.txt gesetzten Alias."""

    def _handle(self, kwargs, response_obj, start_time, end_time) -> None:
        target = _read_active()
        if not target:
            return
        alias = _extract_alias(kwargs)
        if alias != target:
            return
        try:
            entry = _build_entry(kwargs, response_obj, start_time, end_time, alias)
            _write(alias, entry)
        except Exception as e:
            try:
                _write(alias, {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "alias": alias,
                    "_logger_error": str(e)[:300],
                })
            except Exception:
                pass

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._handle(kwargs, response_obj, start_time, end_time)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._handle(kwargs, response_obj, start_time, end_time)


active_key_logger_instance = ActiveKeyLogger()
