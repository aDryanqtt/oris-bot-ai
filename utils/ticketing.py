"""
Helpers compartilhados para o fluxo de tickets.
Centraliza prefixos, IDs e verificações usadas por chat, tickets e help.
"""

from typing import Any

OWNER_ID = 666739489502396438
STAFF_ROLE_ID = 1483338058920103936

TICKET_PREFIXES = (
    "ticket-",
    "geral-",
    "suporte-",
    "revenda-",
    "duvida-",
    "dúvida-",
    "💸・compras",
    "🤖・oris-ai",
)


def is_ticket_name(name: str | None) -> bool:
    """Verifica se um nome de canal segue um padrão de ticket."""
    return bool(name) and name.startswith(TICKET_PREFIXES)


def is_ticket_channel(channel: Any) -> bool:
    """Verifica se um objeto de canal parece ser um ticket."""
    return is_ticket_name(getattr(channel, "name", None))


def is_staff_member(member: Any) -> bool:
    """Verifica se o membro tem permissão de staff, admin ou dono."""
    if member is None:
        return False

    if getattr(member, "id", None) == OWNER_ID:
        return True

    perms = getattr(member, "guild_permissions", None)
    if perms and getattr(perms, "administrator", False):
        return True

    return any(
        getattr(role, "id", None) == STAFF_ROLE_ID
        for role in getattr(member, "roles", [])
    )
