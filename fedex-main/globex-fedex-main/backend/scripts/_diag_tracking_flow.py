"""Diagnostic suivi colis — exécuter depuis backend avec PYTHONPATH=."""
from __future__ import annotations

from unittest.mock import MagicMock

MSG = "tu peux me suivre le colis de numero 881396941965"
TN = "881396941965"


def main() -> None:
    from app.services.llm.tracking_extract import extract_tracking_number
    from app.services.client_reply_safety import (
        is_generic_tracking_boilerplate,
        is_legitimate_tracking_turn,
        repair_client_tracking_reply,
    )
    from app.services.client_agent.facts import fetch_shipment_turn
    from app.services.client_agent.tool_bridge import finalize_client_tracking_turn
    from app.core.config import get_settings

    settings = get_settings()
    print("=== CONFIG ===")
    print(f"llm_enabled={settings.llm_enabled}")
    print(f"gpt_tools_enabled={settings.gpt_tools_enabled}")
    print(f"client_tool_loop_enabled={settings.client_tool_loop_enabled}")
    print(f"fedex_enabled={settings.fedex_enabled}")
    print(f"ollama_model={settings.ollama_model}")

    extracted = extract_tracking_number(MSG)
    print(f"\n=== EXTRACT ===\nmessage TN: {extracted}")

    generic = (
        "Bonjour Amine, Je vous remercie pour votre message. "
        "Pouvez-vous me fournir le numéro de suivi ou d'autres informations nécessaires "
        "pour suivre votre colis ? Sans ces détails, je ne peux pas effectuer de recherche."
    )
    print(f"\n=== BOILERPLATE ===\n{is_generic_tracking_boilerplate(generic, tracking_number=TN, message=MSG)}")
    print(f"legitimate_turn={is_legitimate_tracking_turn(MSG, tracking_number=TN, fedex_error_code=None)}")

    db = MagicMock()
    user = MagicMock()
    user.id = 1
    user.full_name = "Amine"
    user.preferred_language = "fr"
    session = MagicMock()
    session.id = 7

    print("\n=== FEDEX PREFETCH (real) ===")
    try:
        facts = fetch_shipment_turn(db, 1, TN, MSG, tracking_source="message")
        print(f"error_code={facts.error_code}")
        print(f"has_shipment={bool(facts.shipment_data)}")
        print(f"context_len={len(facts.fedex_context_json or '')}")
        print(f"context_preview={(facts.fedex_context_json or '')[:200]}")
    except Exception as exc:
        print(f"PREFETCH FAILED: {exc}")
        facts = None

    fedex_context = facts.fedex_context_json if facts else None
    print("\n=== REPAIR ===")
    fixed = repair_client_tracking_reply(
        generic,
        message=MSG,
        tracking_number=TN,
        fedex_error_code=facts.error_code if facts else None,
        fedex_context_json=fedex_context,
        ui_language="fr",
        preferred_name="Amine",
    )
    print(f"fixed_has_tn={TN in fixed}")
    print(f"still_asks={'fournir le numéro' in fixed.lower()}")
    print(f"reply_preview={fixed[:300]}")

    print("\n=== FINALIZE ===")
    final, tn_out, _ = finalize_client_tracking_turn(
        reply=generic,
        message=MSG,
        resolved_tracking=TN,
        fedex_facts=facts,
        fedex_context=fedex_context,
        tools_used=[],
        lang="fr",
        preferred_name="Amine",
        conversation_history=None,
        db=db,
        user=user,
        session=session,
    )
    print(f"final_has_tn={TN in final}")
    print(f"final_preview={final[:300]}")


if __name__ == "__main__":
    main()
