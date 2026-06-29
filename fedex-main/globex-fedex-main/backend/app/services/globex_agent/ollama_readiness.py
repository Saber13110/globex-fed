"""État Ollama avec cache TTL — probe informatif pour health sidebar uniquement.

Ne bloque pas le chat admin : le kernel tente toujours Ollama (pattern client).
"""

from __future__ import annotations

import time

from app.core.config import get_settings

_CACHE: dict[str, float | bool | None] = {"ok": None, "checked_at": 0.0}
_CACHE_TTL_SECONDS = 45.0


def _probe_ollama_inference() -> bool:
    """Vérifie que Ollama peut réellement inférer (pas seulement lister les modèles)."""
    settings = get_settings()
    if not settings.llm_enabled:
        return False
    try:
        import httpx

        base = settings.ollama_base_url.rstrip("/")
        body = {
            "model": settings.ollama_model,
            "prompt": "ok",
            "stream": False,
            "options": {"num_predict": 4},
        }
        with httpx.Client(timeout=httpx.Timeout(connect=3.0, read=8.0, write=3.0, pool=2.0)) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            if resp.status_code != 200:
                return False
            data = resp.json()
            return bool((data.get("response") or "").strip())
    except Exception:
        return False


def ollama_inference_ready(*, force: bool = False) -> bool:
    """Retourne True si Ollama peut inférer ; résultat mis en cache ~45 s."""
    now = time.time()
    cached_ok = _CACHE.get("ok")
    checked_at = float(_CACHE.get("checked_at") or 0.0)
    if not force and cached_ok is not None and (now - checked_at) < _CACHE_TTL_SECONDS:
        return bool(cached_ok)
    ok = _probe_ollama_inference()
    _CACHE["ok"] = ok
    _CACHE["checked_at"] = now
    return ok


def invalidate_ollama_readiness_cache() -> None:
    """Force un nouveau probe au prochain appel."""
    _CACHE["ok"] = None
    _CACHE["checked_at"] = 0.0
