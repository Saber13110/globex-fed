"""Validation Ollama client — étapes B et C avant branchement chat Phase 1.

Prérequis manuels (étape A) :
  1. ollama serve
  2. ollama pull qwen2.5:7b-instruct  (ou le modèle de OLLAMA_MODEL)
  3. ollama run <model> puis « bonjour » pour précharger
  4. ollama ps — modèle en mémoire recommandé
  5. venv activé depuis backend/

Usage :
  cd fedex-main/globex-fedex-main/backend
  python scripts/validate_ollama_client.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Permet l'exécution : python scripts/validate_ollama_client.py
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import httpx

from app.core.config import get_settings
from app.services.llm.providers import LlmProviderError, call_ollama, call_ollama_simple


@dataclass
class StepResult:
    name: str
    ok: bool
    seconds: float
    detail: str
    preview: str = ""


def _print_checklist() -> None:
    print("=" * 60)
    print("Prérequis manuels (étape A)")
    print("=" * 60)
    print("  1. ollama serve")
    print("  2. ollama pull <OLLAMA_MODEL>")
    print("  3. ollama run <model> + « bonjour » (préchargement)")
    print("  4. ollama ps — vérifier modèle en mémoire")
    print("  5. venv activé, lancer depuis backend/")
    print()


def _print_config() -> None:
    settings = get_settings()
    print("=" * 60)
    print("Configuration")
    print("=" * 60)
    print(f"  LLM_ENABLED          = {settings.llm_enabled}")
    print(f"  LLM_PRIMARY_PROVIDER = {settings.llm_primary_provider}")
    print(f"  OLLAMA_BASE_URL      = {settings.ollama_base_url}")
    print(f"  OLLAMA_MODEL         = {settings.ollama_model}")
    print(f"  OLLAMA_TIMEOUT_SEC   = {settings.ollama_timeout_seconds}")
    print()


def _step_tags() -> StepResult:
    settings = get_settings()
    base = settings.ollama_base_url.rstrip("/")
    model = settings.ollama_model
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base}/api/tags")
        elapsed = time.perf_counter() - t0
        if resp.status_code != 200:
            return StepResult(
                "1. GET /api/tags",
                False,
                elapsed,
                f"HTTP {resp.status_code}",
            )
        data = resp.json()
        names: list[str] = []
        for item in data.get("models") or []:
            if isinstance(item, dict):
                n = item.get("name") or item.get("model") or ""
                if n:
                    names.append(str(n))
        found = any(model in n or n.startswith(model) for n in names)
        detail = f"modèles visibles: {len(names)}"
        if not found:
            detail += f" — '{model}' absent de la liste"
        return StepResult("1. GET /api/tags", found, elapsed, detail)
    except Exception as exc:
        return StepResult(
            "1. GET /api/tags",
            False,
            time.perf_counter() - t0,
            str(exc),
        )


def _step_b_minimal_generate() -> StepResult:
    settings = get_settings()
    base = settings.ollama_base_url.rstrip("/")
    model = settings.ollama_model
    read_timeout = max(float(settings.ollama_timeout_seconds), 120.0)
    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=5.0)
    body: dict[str, Any] = {
        "model": model,
        "prompt": "Dis bonjour en une phrase.",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 64,
            "num_ctx": 512,
        },
    }
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
        elapsed = time.perf_counter() - t0
        reply = (data.get("response") or "").strip()
        if not reply and isinstance(data.get("message"), dict):
            reply = (data["message"].get("content") or "").strip()
        if not reply:
            return StepResult("2. HTTP /api/generate (minimal)", False, elapsed, "réponse vide")
        return StepResult(
            "2. HTTP /api/generate (minimal)",
            True,
            elapsed,
            "OK",
            reply[:150],
        )
    except Exception as exc:
        return StepResult(
            "2. HTTP /api/generate (minimal)",
            False,
            time.perf_counter() - t0,
            str(exc),
        )


def _step_c_call_ollama(lang: str) -> StepResult:
    label = f"3. call_ollama ({lang})"
    t0 = time.perf_counter()
    try:
        reply = call_ollama(
            "Dis bonjour en une phrase courte.",
            ui_language=lang,
            intent="general",
        )
        elapsed = time.perf_counter() - t0
        if not (reply or "").strip():
            return StepResult(label, False, elapsed, "réponse vide")
        return StepResult(label, True, elapsed, "OK", reply.strip()[:150])
    except LlmProviderError as exc:
        return StepResult(label, False, time.perf_counter() - t0, str(exc))
    except Exception as exc:
        return StepResult(label, False, time.perf_counter() - t0, str(exc))


def _step_d_call_ollama_simple(lang: str) -> StepResult:
    label = f"4. call_ollama_simple ({lang}) [chat Phase 1]"
    t0 = time.perf_counter()
    try:
        reply = call_ollama_simple(
            "Dis bonjour en une phrase courte.",
            ui_language=lang,
        )
        elapsed = time.perf_counter() - t0
        if not (reply or "").strip():
            return StepResult(label, False, elapsed, "réponse vide")
        return StepResult(label, True, elapsed, "OK", reply.strip()[:150])
    except LlmProviderError as exc:
        return StepResult(label, False, time.perf_counter() - t0, str(exc))
    except Exception as exc:
        return StepResult(label, False, time.perf_counter() - t0, str(exc))


def _print_results(results: list[StepResult]) -> None:
    print("=" * 60)
    print("Résultats")
    print("=" * 60)
    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"  [{status}] {r.name} — {r.seconds:.1f}s — {r.detail}")
        if r.preview:
            print(f"         -> {r.preview!r}")
    print()


def _print_diagnosis(results: list[StepResult]) -> None:
    by_name = {r.name: r for r in results}
    b = by_name.get("2. HTTP /api/generate (minimal)")
    d_fr = by_name.get("4. call_ollama_simple (fr) [chat Phase 1]")
    c_fr = by_name.get("3. call_ollama (fr)")
    print("=" * 60)
    print("Diagnostic")
    print("=" * 60)
    if b and not b.ok:
        print("  B KO -> infra Ollama (service arrete, URL, modele non pull).")
    elif b and b.ok and d_fr and not d_fr.ok:
        print("  B OK, D KO -> verifier call_ollama_simple ou timeout.")
        print("  -> Precharger avec ollama run ; OLLAMA_TIMEOUT_SECONDS=300")
    elif b and b.ok and d_fr and d_fr.ok:
        print("  B et D OK -> chemin chat Phase 1 (call_ollama_simple) pret.")
        if c_fr and c_fr.ok:
            print(f"  (ref: call_ollama complet = {c_fr.seconds:.1f}s, simple = {d_fr.seconds:.1f}s)")
    else:
        print("  Verifier les etapes en echec ci-dessus.")
    print()


def main() -> int:
    _print_checklist()
    _print_config()

    results = [
        _step_tags(),
        _step_b_minimal_generate(),
        _step_c_call_ollama("fr"),
        _step_c_call_ollama("en"),
        _step_d_call_ollama_simple("fr"),
    ]
    _print_results(results)
    _print_diagnosis(results)

    required_ok = results[1].ok and results[4].ok  # B + D FR (chemin chat)
    c_fr = results[2]
    en = results[3]
    if not c_fr.ok:
        print("Note: call_ollama complet (fr) en echec — non bloquant si D OK.")
    if not en.ok:
        print("Note: call_ollama (en) en echec — non bloquant.")
    print("=" * 60)
    if required_ok:
        print("VALIDATION OK — B + call_ollama_simple (fr) reussis.")
        print("=" * 60)
        return 0
    print("VALIDATION ECHOUEE — corriger avant Phase 1 chat.")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    sys.exit(main())
