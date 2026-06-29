"""Centre de rapports admin — pipeline Jarvis."""

__all__ = ["is_reports_workspace", "try_admin_reports_turn"]


def __getattr__(name: str):
    if name == "try_admin_reports_turn":
        from app.services.admin_client.reports.reports_executor import try_admin_reports_turn

        return try_admin_reports_turn
    if name == "is_reports_workspace":
        from app.services.admin_client.reports.reports_workspace import is_reports_workspace

        return is_reports_workspace
    raise AttributeError(name)
