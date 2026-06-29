"""Capacités client réutilisées côté admin.

Les modules client (`client_phase*`) lisent `client_agent_capabilities` et
`client_agent_router_enabled` du portail client. Pour réutiliser ce code côté admin
sans modifier le comportement du portail client, on active temporairement les
capacités admin pendant l'exécution du pipeline admin, puis on restaure la config.
"""

from __future__ import annotations

import contextlib

from app.core.config import get_settings

CAP_FEDEX = "fedex"
CAP_PDF = "pdf"
CAP_EXCEL = "excel"
CAP_DOCUMENT_READ = "document_read"
CAP_NOTIFICATIONS = "notifications"


def admin_capabilities() -> frozenset[str]:
    raw = get_settings().admin_client_capabilities or ""
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def has_admin_capability(cap: str) -> bool:
    return cap.lower() in admin_capabilities()


@contextlib.contextmanager
def admin_client_capability_context():
    """Active temporairement les capacités client requises par les modules réutilisés.

    Fusionne `chat` + les capacités admin et force le routeur sémantique, puis restaure
    la configuration du portail client en sortie (y compris en cas d'exception).
    """
    settings = get_settings()
    prev_caps = settings.client_agent_capabilities
    prev_router = settings.client_agent_router_enabled

    merged = {"chat", *admin_capabilities()}
    settings.client_agent_capabilities = ",".join(sorted(merged))
    settings.client_agent_router_enabled = True
    try:
        yield
    finally:
        settings.client_agent_capabilities = prev_caps
        settings.client_agent_router_enabled = prev_router
