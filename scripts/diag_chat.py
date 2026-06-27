#!/usr/bin/env python3
"""Diagnostic chat fedex-v0 + Ollama — mesure chaque étape."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Charge .env
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


async def test_ollama_simple() -> tuple[bool, float, str]:
    import httpx

    url = "http://localhost:11434/api/generate"
    payload = {"model": "llama3.2:3b", "prompt": "Dis bonjour en 5 mots.", "stream": False}
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            text = r.json().get("response", "")[:200]
            return True, time.perf_counter() - t0, text
    except Exception as e:
        return False, time.perf_counter() - t0, str(e)


async def test_ollama_chat_stream() -> tuple[bool, float, str]:
    import httpx

    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "bonjour"}],
        "stream": True,
        "think": False,
    }
    t0 = time.perf_counter()
    first_chunk_at: float | None = None
    full = ""
    try:
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    import json

                    data = json.loads(line)
                    delta = data.get("message", {}).get("content", "")
                    if delta and first_chunk_at is None:
                        first_chunk_at = time.perf_counter() - t0
                    full += delta
                    if data.get("done"):
                        break
        detail = f"1er token: {first_chunk_at:.1f}s | total: {time.perf_counter() - t0:.1f}s | {full[:150]}"
        return bool(full.strip()), time.perf_counter() - t0, detail
    except Exception as e:
        return False, time.perf_counter() - t0, str(e)


async def test_ollama_fedex_v0_sized_prompt() -> tuple[bool, float, str]:
    """Simule le prompt système fedex-v0 (statique + skills)."""
    import httpx

    static_path = ROOT / "prompts" / "system_static.md"
    system = static_path.read_text(encoding="utf-8") if static_path.exists() else "Tu es fedex-v0."
    print(f"  Taille prompt système: {len(system):,} caractères")

    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "llama3.2:3b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "bonjour"},
        ],
        "stream": True,
        "think": False,
        "options": {"temperature": 0.7},
    }
    t0 = time.perf_counter()
    first_chunk_at: float | None = None
    full = ""
    try:
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    import json

                    data = json.loads(line)
                    delta = data.get("message", {}).get("content", "")
                    if delta and first_chunk_at is None:
                        first_chunk_at = time.perf_counter() - t0
                    full += delta
                    if data.get("done"):
                        break
        detail = f"1er token: {first_chunk_at:.1f}s | total: {time.perf_counter() - t0:.1f}s | {full[:150]}"
        return bool(full.strip()), time.perf_counter() - t0, detail
    except Exception as e:
        return False, time.perf_counter() - t0, str(e)


async def test_fedex_v0_gateway() -> tuple[bool, float, str]:
    """Appelle le Gateway fedex-v0 directement (sans HTTP)."""
    t0 = time.perf_counter()
    try:
        from fedex_v0.bootstrap import build

        container = build()
        gateway = container.gateway
        session, route, response = await gateway.handle(
            message="bonjour",
            session_id=None,
            stream=False,
        )
        if isinstance(response, str):
            text = response
        else:
            chunks = []
            async for c in response:
                chunks.append(c)
            text = "".join(chunks)
        detail = f"route={route.value} | session={session.id} | {text[:200]}"
        return bool(text.strip()), time.perf_counter() - t0, detail
    except Exception as e:
        import traceback

        return False, time.perf_counter() - t0, f"{e}\n{traceback.format_exc()[-500:]}"


async def main() -> None:
    from fedex_v0.kernel.settings import settings

    print("DIAGNOSTIC FEDEX_V0 CHAT")
    print(f"LLM_PROVIDER={settings.llm_provider} | OLLAMA_MODEL={settings.ollama_model}")

    # 1. Ollama simple
    section("1. Ollama /api/generate (prompt court)")
    ok, dt, detail = await test_ollama_simple()
    print(f"  {'OK' if ok else 'ECHEC'} ({dt:.1f}s): {detail}")

    if not ok:
        print("\n>>> BLOCAGE: Ollama ne répond pas. Relancez l'app Ollama depuis Windows.")
        return

    # 2. Ollama chat stream
    section("2. Ollama /api/chat stream (message simple)")
    ok2, dt2, detail2 = await test_ollama_chat_stream()
    print(f"  {'OK' if ok2 else 'ECHEC'} ({dt2:.1f}s): {detail2}")

    # 3. Ollama avec gros prompt fedex-v0
    section("3. Ollama avec prompt système fedex-v0 (~{size})".format(
        size="voir ci-dessous"
    ))
    ok3, dt3, detail3 = await test_ollama_fedex_v0_sized_prompt()
    print(f"  {'OK' if ok3 else 'ECHEC'} ({dt3:.1f}s): {detail3}")

    if ok3 and dt3 > 90:
        print("\n>>> GOULOT: prompt fedex-v0 trop lourd pour CPU — 1ère réponse > 90s.")

    # 4. Gateway fedex-v0 complet
    section("4. Gateway fedex-v0 complet (pipeline réel)")
    ok4, dt4, detail4 = await test_fedex_v0_gateway()
    print(f"  {'OK' if ok4 else 'ECHEC'} ({dt4:.1f}s): {detail4}")

    section("CONCLUSION")
    if not ok4:
        if ok3 and dt3 > 60:
            print("  Cause: Ollama + gros prompt fedex-v0 = trop lent sur CPU.")
            print("  Fix: clé API cloud (OpenAI) OU PC plus puissant OU réduire le prompt.")
        elif not ok2:
            print("  Cause: Ollama chat/stream défaillant.")
        else:
            print("  Cause: bug dans le pipeline Gateway (pas Ollama seul).")
    else:
        print(f"  Le pipeline fonctionne mais prend {dt4:.0f}s.")
        if dt4 > 60:
            print("  Le navigateur timeout avant la réponse → bulle FEDEX_V0 vide.")


if __name__ == "__main__":
    asyncio.run(main())
