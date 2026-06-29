"""Gestion utilisateurs admin — pipeline Jarvis."""

__all__ = ["is_users_workspace", "try_admin_users_turn"]


def __getattr__(name: str):
    if name == "try_admin_users_turn":
        from app.services.admin_client.users.users_executor import try_admin_users_turn

        return try_admin_users_turn
    if name == "is_users_workspace":
        from app.services.admin_client.users.users_workspace import is_users_workspace

        return is_users_workspace
    raise AttributeError(name)
