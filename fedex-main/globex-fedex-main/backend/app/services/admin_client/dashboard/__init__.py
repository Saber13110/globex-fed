"""Dashboard admin — collector, intents, executor (Jarvis admin_client)."""

__all__ = ["is_dashboard_workspace", "try_admin_dashboard_turn"]


def __getattr__(name: str):
    if name == "try_admin_dashboard_turn":
        from app.services.admin_client.dashboard.dashboard_executor import try_admin_dashboard_turn

        return try_admin_dashboard_turn
    if name == "is_dashboard_workspace":
        from app.services.admin_client.dashboard.dashboard_workspace import is_dashboard_workspace

        return is_dashboard_workspace
    raise AttributeError(name)
