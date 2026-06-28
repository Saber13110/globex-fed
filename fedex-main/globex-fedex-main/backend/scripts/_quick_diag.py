from app.services.llm.tracking_extract import extract_tracking_number
from app.services.chat_session_context import resolve_tracking_for_message
from app.services.client_reply_safety import is_generic_tracking_boilerplate, repair_client_tracking_reply
from unittest.mock import MagicMock

MSG = "tu peux me suivre le colis de numero 881396941965"
TN = "881396941965"
GENERIC = (
    "Bonjour Amine, Je vous remercie pour votre message. "
    "Pouvez-vous me fournir le numéro de suivi ou d'autres informations nécessaires "
    "pour suivre votre colis ? Sans ces détails, je ne peux pas effectuer de recherche."
)

print("extract:", extract_tracking_number(MSG))
db = MagicMock()
db.scalars.return_value.all.return_value = []
tn, src = resolve_tracking_for_message(db, session_id=1, user_id=1, message=MSG, conversation_history="")
print("resolve:", tn, src)
print("boilerplate:", is_generic_tracking_boilerplate(GENERIC, tracking_number=TN, message=MSG))
fixed = repair_client_tracking_reply(
    GENERIC,
    message=MSG,
    tracking_number=TN,
    fedex_error_code="fedex_not_found",
    fedex_context_json='{"tracking_number":"881396941965","available":false,"reason":"fedex_not_found"}',
    ui_language="fr",
    preferred_name="Amine",
)
print("fixed has TN:", TN in fixed)
print("fixed:", fixed[:250])
