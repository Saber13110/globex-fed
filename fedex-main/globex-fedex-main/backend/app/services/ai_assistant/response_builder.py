"""Normalisation des réponses Copilot admin pour le frontend."""

from __future__ import annotations

from typing import Any


def _resolve_mode(raw: dict[str, Any]) -> str:
    explicit = (raw.get("mode") or "").strip().lower()
    if explicit in {"jarvis", "gemini", "gemini_pro", "ollama", "local_fallback", "timeout_fallback"}:
        return explicit
    provider = (raw.get("llm_provider") or "").strip().lower()
    if provider == "gemini_pro":
        return "gemini_pro"
    if provider == "gemini":
        return "gemini"
    if provider in {"jarvis", "ollama"}:
        return provider
    if provider in {"local", "deterministic", "degraded"}:
        return "local_fallback"
    if raw.get("llm_degraded"):
        return "local_fallback"
    return "jarvis"


def _resolve_confidence(raw: dict[str, Any], mode: str) -> float:
    if raw.get("confidence") is not None:
        try:
            return max(0.0, min(1.0, float(raw["confidence"])))
        except (TypeError, ValueError):
            pass
    tools = raw.get("tools_used") or []
    reply = (raw.get("reply") or "").strip()
    if not reply:
        return 0.0
    if "quota API Gemini" in reply or "n'ai pas pu joindre" in reply:
        return 0.2
    if tools and mode in {"gemini", "jarvis"}:
        return 0.92
    if tools:
        return 0.88
    if mode == "local_fallback":
        return 0.75
    if mode == "ollama" or mode == "jarvis":
        return 0.82
    return 0.85


def _reasoning_summary(raw: dict[str, Any]) -> str | None:
    if raw.get("reasoning_summary"):
        return str(raw["reasoning_summary"])[:500]
    reasoning = raw.get("agent_reasoning")
    if isinstance(reasoning, dict):
        objective = (reasoning.get("objective") or "").strip()
        plan = reasoning.get("plan") or []
        if objective and plan:
            return f"{objective} → {' ; '.join(str(p) for p in plan[:4])}"
        if objective:
            return objective[:500]
    tools = raw.get("tools_used") or []
    if tools:
        return f"Consultation des outils : {', '.join(tools)}."
    return None


def _detect_error(reply: str, raw: dict[str, Any]) -> str | None:
    if raw.get("error"):
        return str(raw["error"])
    lower = (reply or "").lower()
    if "quota api gemini" in lower or "erreur 429" in lower:
        return "gemini_quota_exceeded"
    if "clé api gemini refusée" in lower or "erreur 401" in lower:
        return "gemini_auth_failed"
    if "ollama indisponible" in lower or "timed out" in lower:
        return "ollama_timeout"
    return None


def enrich_copilot_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Ajoute answer, mode, confidence, reasoning_summary, error (compat API existante)."""
    out = dict(raw)
    reply = (out.get("reply") or out.get("answer") or "").strip()
    out["reply"] = reply
    out["answer"] = reply
    mode = _resolve_mode(out)
    out["mode"] = mode
    out["confidence"] = _resolve_confidence(out, mode)
    out["reasoning_summary"] = _reasoning_summary(out)
    out["error"] = _detect_error(reply, out)
    if raw.get("language"):
        out["language"] = raw["language"]
    elif raw.get("ui_language"):
        out["language"] = raw["ui_language"]
    if raw.get("execution_time_ms") is not None:
        out["execution_time_ms"] = raw["execution_time_ms"]
    if raw.get("sources_used") is not None:
        out["sources_used"] = raw["sources_used"]
    if raw.get("requires_confirmation") is not None:
        out["requires_confirmation"] = raw["requires_confirmation"]
    if raw.get("suggested_action") is not None:
        out["suggested_action"] = raw["suggested_action"]
    if raw.get("export_preview") is not None:
        out["export_preview"] = raw["export_preview"]
    if raw.get("export_status") is not None:
        out["export_status"] = raw["export_status"]
    if raw.get("export_result") is not None:
        out["export_result"] = raw["export_result"]
    if raw.get("export_download"):
        out["download_url"] = raw["export_download"].get("url") or raw["export_download"].get("download_url")
        out["file_name"] = out["file_name"] or raw["export_download"].get("filename")
    if raw.get("download_url"):
        out["download_url"] = raw["download_url"]
    if raw.get("file_name"):
        out["file_name"] = raw["file_name"]
    # Sanitize answer — jamais JSON brut
    from app.services.ai_assistant.response_sanitizer import sanitize_reply
    tool_payloads = [{"name": t, "response": {}} for t in (raw.get("tools_used") or [])]
    out["answer"] = sanitize_reply(out["answer"], tool_payloads=tool_payloads if raw.get("tools_used") else None)
    out["reply"] = out["answer"]
    return out


def build_timeout_fallback_response(
    *,
    intent: str = "timeout",
    tools_used: list[str] | None = None,
) -> dict[str, Any]:
    """Réponse obligatoire si le timeout global est atteint."""
    return enrich_copilot_response(
        {
            "reply": (
                "Je n'ai pas pu terminer l'analyse dans le délai prévu. "
                "Certains services ou outils ont mis trop de temps à répondre."
            ),
            "intent": intent,
            "agent_type": "summary",
            "agent_type_label": "Jarvis",
            "analysis_only": True,
            "llm_degraded": True,
            "llm_provider": "timeout_fallback",
            "mode": "timeout_fallback",
            "tools_used": tools_used or [],
            "confidence": 0.3,
            "reasoning_summary": "Timeout global atteint pendant l'exécution.",
            "error": "TIMEOUT",
        }
    )


def build_error_fallback_response(detail: str = "") -> dict[str, Any]:
    """Réponse sûre si le pipeline copilot lève une exception."""
    msg = (
        "Je n'ai pas pu traiter votre demande pour le moment. "
        "Réessayez dans quelques secondes ou reformulez votre question."
    )
    if detail and "timeout" in detail.lower():
        msg = (
            "Le moteur IA met trop de temps à répondre (timeout). "
            "Réessayez une question plus courte ou vérifiez qu'Ollama tourne si Gemini est saturé."
        )
    return enrich_copilot_response(
        {
            "reply": msg,
            "intent": "error",
            "agent_type": "summary",
            "agent_type_label": "Jarvis",
            "analysis_only": True,
            "llm_degraded": True,
            "llm_provider": "local",
            "tools_used": [],
            "error": "pipeline_exception",
        }
    )
