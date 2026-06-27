"""Liste blanche des numéros de suivi autorisés en environnement FedEx sandbox."""

from __future__ import annotations

from app.core.config import get_settings


class FedExSandboxWhitelistError(Exception):
    """Numéro hors liste blanche sandbox — pas d'appel API FedEx."""

    code = "sandbox_whitelist_denied"

    def __init__(self, tracking_number: str) -> None:
        self.tracking_number = tracking_number.strip().upper()
        super().__init__(SANDBOX_WHITELIST_MESSAGE)


SANDBOX_WHITELIST_MESSAGE = (
    "Ce numéro de suivi n'est pas autorisé en environnement sandbox FedEx. "
    "Utilisez un numéro de test fourni par FedEx pour la démonstration."
)

# Message injecté au LLM pour le portail client (ton conseiller, pas jargon technique).
CLIENT_TRACKING_NOT_FOUND_HINT = (
    "Aucun colis n'a été trouvé pour ce numéro de suivi dans FedEx. "
    "Le numéro est peut-être incorrect, incomplet ou pas encore actif dans le réseau."
)

FEDEX_SANDBOX_WHITELIST: frozenset[str] = frozenset(
    {
        "881354459588",
        "881103296010",
        "881396941965",
        "880898436686",
        "880894166593",
        "881335098247",
        "429807310760",
        "817724891022",
        "446856788071",
        "880924781346",
        "881020391412",
        "817621747293",
        "880903665143",
        "881390370213",
        "817725038324",
        "881107806551",
        "817727782285",
        "456092427664",
        "817947476462",
        "456092428010",
        "817725679239",
        "456092427388",
        "881135077232",
        "817725683025",
        "817724891114",
        "456092426999",
        "456092427333",
        "881304337406",
        "817581472369",
        "881109161158",
        "456092427907",
        "429807311241",
        "880849626649",
        "817947500335",
        "881107662155",
        "881390186066",
        "817950452196",
        "880892017122",
        "456092426554",
        "881389693790",
        "817947476429",
        "456092426061",
        "817947500427",
        "880903443485",
        "881479084025",
        "772490509535",
        "881153569524",
        "880850129464",
        "456092426793",
        "817947500405",
        "881144017356",
        "817943541991",
        "881304991546",
        "817947500416",
        "743761563777",
        "881020684420",
        "881456408620",
        "817727791945",
        "881283278515",
        "817782011791",
        "881027580470",
        "881017573629",
        "817943542093",
        "716726841639",
        "881223865218",
        "817621878505",
        "817581472406",
        "880953388747",
        "881424676119",
        "817725643764",
        "627133572309",
        "880809093440",
        "817943638299",
        "881427688784",
        # Colis démo multi-étapes (suivi chat / surveillance agent)
        "397773675776",
    }
)


def is_fedex_sandbox() -> bool:
    base = (get_settings().fedex_base_url or "").lower()
    return "apis-sandbox.fedex.com" in base


def is_whitelisted_tracking_number(tracking_number: str) -> bool:
    return tracking_number.strip().upper() in FEDEX_SANDBOX_WHITELIST


def sandbox_whitelist_applies() -> bool:
    settings = get_settings()
    return settings.fedex_enabled and is_fedex_sandbox()


def assert_sandbox_whitelist(tracking_number: str) -> None:
    if not sandbox_whitelist_applies():
        return
    normalized = tracking_number.strip().upper()
    if not is_whitelisted_tracking_number(normalized):
        raise FedExSandboxWhitelistError(normalized)
