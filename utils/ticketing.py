"""
Helpers compartilhados para o fluxo de tickets.
Centraliza prefixos, IDs e verificacoes usadas por chat e tickets.
"""

from typing import Any

OWNER_ID = 666739489502396438
STAFF_ROLE_ID = 1483338058920103936

STRICT_TICKET_PREFIXES = (
    "ticket-",
    "geral-",
    "suporte-",
    "revenda-",
    "duvida-",
    "dúvida-",
)

TICKET_ROUTING_PREFIXES = (
    *STRICT_TICKET_PREFIXES,
    "💸・compras",
    "🤖・oris-ai",
)


def is_ticket_name(name: str | None, *, include_routing: bool = False) -> bool:
    """Verifica se um nome de canal segue um padrao de ticket."""
    prefixes = TICKET_ROUTING_PREFIXES if include_routing else STRICT_TICKET_PREFIXES
    return bool(name) and name.startswith(prefixes)


def is_ticket_routing_name(name: str | None) -> bool:
    """Verifica se o nome deve ser tratado como rota automatica de ticket."""
    return is_ticket_name(name, include_routing=True)


def is_ticket_channel(channel: Any, *, include_routing: bool = False) -> bool:
    """Verifica se um objeto de canal parece ser um ticket."""
    return is_ticket_name(getattr(channel, "name", None), include_routing=include_routing)


def is_ticket_routing_channel(channel: Any) -> bool:
    """Verifica se o canal entra no roteamento automatico de atendimento."""
    return is_ticket_channel(channel, include_routing=True)


def is_staff_member(member: Any) -> bool:
    """Verifica se o membro tem permissao de staff, admin ou dono."""
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
