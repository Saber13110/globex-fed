# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Types partagés du noyau assistant client."""
#
# from __future__ import annotations
#
# from dataclasses import dataclass, field
# from typing import Any
#
#
# @dataclass
# class ClientTurnResult:
#     reply: str
#     source: str
#     intent: str
#     tracking_number: str | None = None
#     llm_provider: str | None = None
#     shipment: dict[str, Any] | None = None
#     agent_mode: bool | None = field(default=None)
#     export_download: dict[str, Any] | None = None
#     tools_used: list[str] | None = None
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""Types client_agent — stub Phase 0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClientTurnResult:
    reply: str
    source: str
    intent: str
    tracking_number: str | None = None
    llm_provider: str | None = None
    shipment: dict[str, Any] | None = None
    agent_mode: bool | None = field(default=None)
    export_download: dict[str, Any] | None = None
    tools_used: list[str] | None = None
