"""Smoke perf Globex Agent — architecture client-like (ollama_chat par défaut)."""

from __future__ import annotations

import sys
import time
from unittest.mock import patch

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.user import User
from app.services.globex_agent.kernel import run_globex_agent_chat


def main() -> int:
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.role == "admin").limit(1)).scalar_one_or_none()
        if admin is None:
            print("ERREUR: aucun admin en base")
            return 1

        chat_reply = "Je suis Jarvis — colis, utilisateurs, tickets, logs, KPI et exports."

        with patch(
            "app.services.globex_agent.kernel.admin_ollama_chat",
            return_value=chat_reply,
        ), patch(
            "app.services.globex_agent.kernel.plan_admin_platform_task",
            return_value=None,
        ):
            cases = [
                ("bonjour", ["ollama_chat"]),
                ("comment tu peux m'aider", ["ollama_chat"]),
                ("tu peux faire quoi", ["ollama_chat"]),
            ]
            failed = 0
            for msg, expected_tools in cases:
                t0 = time.perf_counter()
                r = run_globex_agent_chat(db, admin, msg, agent_mode=True, ui_language="fr")
                ms = (time.perf_counter() - t0) * 1000
                ok = r.get("tools_used") == expected_tools and "ollama_skip" not in (
                    r.get("tools_used") or []
                )
                status = "OK" if ok else "FAIL"
                print(f"[{status}] {msg!r} tools={r.get('tools_used')} ms={ms:.0f}")
                if not ok:
                    failed += 1

            from app.services.llm.providers import LlmProviderError

            with patch(
                "app.services.globex_agent.kernel.admin_ollama_chat",
                side_effect=LlmProviderError("down"),
            ):
                t0 = time.perf_counter()
                r = run_globex_agent_chat(
                    db, admin, "question vague hors sujet", agent_mode=True, ui_language="fr",
                )
                ms = (time.perf_counter() - t0) * 1000
                ok = (
                    r.get("tools_used") == ["ollama_chat"]
                    and r.get("llm_degraded")
                    and "ollama_skip" not in (r.get("tools_used") or [])
                )
                status = "OK" if ok else "FAIL"
                print(
                    f"[{status}] ollama_down tools={r.get('tools_used')} "
                    f"degraded={r.get('llm_degraded')} ms={ms:.0f}"
                )
                if not ok:
                    failed += 1

        health = __import__(
            "app.services.globex_agent.kernel", fromlist=["check_globex_agent_health"],
        ).check_globex_agent_health()
        print(f"[INFO] kernel_version={health.get('kernel_version')} simple_mode={health.get('simple_mode')}")

        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
