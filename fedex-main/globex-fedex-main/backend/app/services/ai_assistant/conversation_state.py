"""Mémoire conversationnelle unifiée — compatible copilot_state existant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationState:
    """État session admin — structure demandée + compatibilité legacy."""

    last_tracking_number: str | None = None
    last_tracking_result: dict[str, Any] | None = None
    last_users_result: dict[str, Any] | None = None
    last_notifications_result: dict[str, Any] | None = None
    last_security_result: dict[str, Any] | None = None
    last_report_result: dict[str, Any] | None = None
    last_ticket_result: dict[str, Any] | None = None
    last_exportable_result: dict[str, Any] | None = None
    last_subject_type: str | None = None
    last_subject_id: str | None = None
    last_intent: str | None = None
    last_language: str = "fr"
    # Legacy aliases
    last_user_list: list[dict[str, Any]] = field(default_factory=list)
    last_notification_list: list[dict[str, Any]] = field(default_factory=list)
    last_report: dict[str, Any] | None = None
    last_security_report: dict[str, Any] | None = None
    last_ticket_report: dict[str, Any] | None = None
    last_exportable_dataset: dict[str, Any] | None = None
    last_selected_user: dict[str, Any] | None = None
    last_exportable_type: str | None = None
    last_logs_result: dict[str, Any] | None = None

    def get_users_list(self) -> list[dict[str, Any]]:
        """Liste utilisateurs mémorisée — legacy + nouveau state."""
        if self.last_user_list:
            return self.last_user_list
        if isinstance(self.last_users_result, dict):
            users = self.last_users_result.get("users") or self.last_users_result.get("admin_accounts")
            if users:
                return [u for u in users if isinstance(u, dict)]
        export = self.last_exportable_result or self.last_exportable_dataset
        if export and export.get("type") == "users":
            return [u for u in (export.get("data") or []) if isinstance(u, dict)]
        return []

    def select_user_at(self, index: int) -> dict[str, Any] | None:
        users = self.get_users_list()
        if 0 <= index < len(users):
            self.last_selected_user = users[index]
            self.last_subject_type = "users"
            self.last_subject_id = str(users[index].get("id") or users[index].get("email") or "")
            return users[index]
        return None

    @classmethod
    def from_copilot_state(cls, state: dict[str, Any] | None) -> ConversationState:
        if not state:
            return cls()
        conv = state.get("conversation_state") or {}
        tracking = conv.get("last_tracking_number") or state.get("last_tracking_number")
        if not tracking and state.get("last_tracking_numbers"):
            tracking = state["last_tracking_numbers"][0]

        export_ds = (
            conv.get("last_exportable_result")
            or conv.get("last_exportable_dataset")
            or state.get("last_exportable_dataset")
        )
        if not export_ds:
            module = state.get("last_module")
            items = state.get("last_items") or []
            if module and items:
                export_ds = {"type": module, "data": items}

        user_list = list(conv.get("last_user_list") or state.get("last_user_list") or [])
        if not user_list and state.get("last_module") == "users":
            user_list = list(state.get("last_items") or [])[:50]

        users_result = conv.get("last_users_result") or state.get("last_users_result")
        if not users_result and user_list:
            users_result = {"users": user_list}

        selected = conv.get("last_selected_user") or state.get("last_selected_user")

        inst = cls(
            last_tracking_number=tracking,
            last_tracking_result=conv.get("last_tracking_result") or state.get("last_tracking_result"),
            last_users_result=users_result,
            last_notifications_result=conv.get("last_notifications_result") or state.get("last_notifications_result"),
            last_security_result=conv.get("last_security_result") or state.get("last_security_result"),
            last_report_result=conv.get("last_report_result") or state.get("last_report_result"),
            last_ticket_result=conv.get("last_ticket_result") or state.get("last_ticket_result"),
            last_exportable_result=export_ds if isinstance(export_ds, dict) else None,
            last_subject_type=conv.get("last_subject_type") or state.get("last_subject_type"),
            last_subject_id=conv.get("last_subject_id") or state.get("last_subject_id"),
            last_intent=conv.get("last_intent") or state.get("last_intent"),
            last_language=conv.get("last_language") or state.get("last_language") or state.get("language") or "fr",
            last_user_list=user_list[:50],
            last_notification_list=list(
                conv.get("last_notification_list") or state.get("last_notifications") or []
            )[:50],
            last_report=conv.get("last_report") or state.get("last_report"),
            last_security_report=conv.get("last_security_report") or state.get("last_security_report"),
            last_ticket_report=conv.get("last_ticket_report") or state.get("last_ticket_report"),
            last_exportable_dataset=export_ds if isinstance(export_ds, dict) else None,
            last_selected_user=selected if isinstance(selected, dict) else None,
            last_exportable_type=(
                conv.get("last_exportable_type")
                or state.get("last_exportable_type")
                or (export_ds.get("type") if isinstance(export_ds, dict) else None)
            ),
            last_logs_result=conv.get("last_logs_result") or state.get("last_logs_result"),
        )
        if not inst.last_subject_type and state.get("last_module") == "users" and user_list:
            inst.last_subject_type = "users"
        return inst

    def to_dict(self) -> dict[str, Any]:
        export = self.last_exportable_result or self.last_exportable_dataset
        return {
            "last_tracking_number": self.last_tracking_number,
            "last_tracking_result": self.last_tracking_result,
            "last_users_result": self.last_users_result,
            "last_notifications_result": self.last_notifications_result,
            "last_security_result": self.last_security_result,
            "last_report_result": self.last_report_result,
            "last_ticket_result": self.last_ticket_result,
            "last_exportable_result": export,
            "last_subject_type": self.last_subject_type,
            "last_subject_id": self.last_subject_id,
            "last_intent": self.last_intent,
            "last_language": self.last_language,
            "last_user_list": self.last_user_list[:50],
            "last_notification_list": self.last_notification_list[:50],
            "last_report": self.last_report,
            "last_security_report": self.last_security_report,
            "last_ticket_report": self.last_ticket_report,
            "last_exportable_dataset": export,
            "last_selected_user": self.last_selected_user,
            "last_exportable_type": self.last_exportable_type or (export.get("type") if isinstance(export, dict) else None),
            "last_logs_result": self.last_logs_result,
        }

    def merge_into_copilot_state(self, state: dict[str, Any]) -> dict[str, Any]:
        out = dict(state)
        out["conversation_state"] = self.to_dict()
        if self.last_tracking_number:
            out["last_tracking_number"] = self.last_tracking_number
            nums = list(out.get("last_tracking_numbers") or [])
            if self.last_tracking_number not in nums:
                nums.insert(0, self.last_tracking_number)
            out["last_tracking_numbers"] = nums[:20]
        export = self.last_exportable_result or self.last_exportable_dataset
        if export:
            out["last_exportable_dataset"] = export
            out["last_exportable_result"] = True
            ds_type = export.get("type")
            if ds_type:
                out["last_module"] = ds_type.replace("_history", "")
                out["last_items"] = export.get("data") or []
        if self.last_intent:
            out["last_intent"] = self.last_intent
        if self.last_language:
            out["last_language"] = self.last_language
            out["language"] = self.last_language
        if self.last_subject_type:
            out["last_subject_type"] = self.last_subject_type
        if self.last_subject_id:
            out["last_subject_id"] = self.last_subject_id
        if self.last_tracking_result:
            out["last_tracking_result"] = self.last_tracking_result
        if self.last_users_result:
            out["last_users_result"] = self.last_users_result
        if self.last_selected_user:
            out["last_selected_user"] = self.last_selected_user
        if self.last_exportable_type:
            out["last_exportable_type"] = self.last_exportable_type
        if self.last_ticket_result:
            out["last_ticket_result"] = self.last_ticket_result
        if self.last_notification_list:
            out["last_notifications"] = self.last_notification_list
        return out

    def enrich_from_tool(self, tool_name: str, payload: dict[str, Any], *, intent: str | None = None) -> None:
        if payload.get("status") == "error":
            return
        if intent:
            self.last_intent = intent

        tn = payload.get("tracking_number")
        if tn or "tracking" in tool_name:
            if tn:
                self.last_tracking_number = str(tn)
            self.last_tracking_result = {k: v for k, v in payload.items() if k != "status"}
            self.last_subject_type = "tracking"
            self.last_subject_id = self.last_tracking_number
            self.last_exportable_result = {
                "type": "tracking",
                "data": [self.last_tracking_result] if self.last_tracking_result else [],
            }
            self.last_exportable_dataset = self.last_exportable_result

        users = payload.get("users") or payload.get("admin_accounts")
        if users and isinstance(users, list):
            self.last_users_result = payload
            self.last_user_list = [u for u in users if isinstance(u, dict)][:50]
            self.last_subject_type = "users"
            self.last_exportable_result = {"type": "users", "data": self.last_user_list}
            self.last_exportable_dataset = self.last_exportable_result

        sample = payload.get("sample")
        if sample and isinstance(sample, list) and not self.last_exportable_result:
            module = "tracking" if "tracking" in tool_name else "logs" if "log" in tool_name else "generic"
            if module != "generic":
                self.last_exportable_result = {"type": module, "data": sample[:50]}
                self.last_exportable_dataset = self.last_exportable_result

        notifs = payload.get("sample") or payload.get("notifications")
        if notifs and isinstance(notifs, list) and "notification" in tool_name:
            self.last_notifications_result = payload
            self.last_notification_list = [n for n in notifs if isinstance(n, dict)][:50]
            self.last_exportable_result = {"type": "notifications", "data": self.last_notification_list}
            self.last_exportable_dataset = self.last_exportable_result

        tickets = payload.get("tickets")
        if tickets and isinstance(tickets, list):
            self.last_ticket_result = {"count": payload.get("count", len(tickets)), "tickets": tickets[:20]}
            self.last_ticket_report = self.last_ticket_result
            self.last_exportable_result = {"type": "tickets", "data": tickets[:50]}
            self.last_exportable_dataset = self.last_exportable_result

        if "security" in tool_name or "generate_security_report" in tool_name:
            self.last_security_result = {k: v for k, v in payload.items() if k != "status"}
            self.last_security_report = self.last_security_result

        if "platform_health" in tool_name or tool_name in {"get_platform_stats", "analyze_platform_health"}:
            self.last_report_result = {k: v for k, v in payload.items() if k != "status"}
            self.last_report = self.last_report_result

    def record_tool_success(self, tool_name: str, payload: dict[str, Any], *, intent: str | None = None) -> None:
        """Alias explicite — chaque outil réussi met à jour le state."""
        self.enrich_from_tool(tool_name, payload, intent=intent)
        from app.services.ai_assistant.context_resolver import update_subject_from_tool
        update_subject_from_tool(self, tool_name, payload)
