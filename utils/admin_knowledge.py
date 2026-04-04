"""
Conhecimento aprovado por administradores.
Seleciona entradas relevantes para o contexto atual do chat.
"""

from __future__ import annotations

import re
import unicodedata

from utils.database import db

STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "sobre", "que", "qual", "quais",
    "como", "quando", "onde", "isso", "isto", "essa", "esse", "essa",
    "ele", "ela", "eles", "elas", "me", "te", "se", "eu", "voce",
    "voces", "pra", "pro", "e", "ou", "mas", "ja", "mais", "muito",
    "muita", "muitos", "muitas", "tem", "tenho", "temos", "tinha",
    "ser", "estar", "esta", "estao", "ta", "to", "vai", "ir",
}


def _normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def _tokenize(text: str) -> set[str]:
    normalized = _normalize(text)
    tokens = set(re.findall(r"[a-z0-9_]{3,}", normalized))
    return {token for token in tokens if token not in STOPWORDS}


def _tag_tokens(tags: str) -> set[str]:
    base = tags.replace(",", " ").replace(";", " ")
    return _tokenize(base)


def _score_entry(entry: dict, query: str, query_tokens: set[str]) -> int:
    trigger_text = entry.get("trigger_text", "")
    answer_text = entry.get("answer_text", "")
    tags_text = entry.get("tags", "")

    trigger_tokens = _tokenize(trigger_text)
    answer_tokens = _tokenize(answer_text)
    tags_tokens = _tag_tokens(tags_text)

    score = 0
    score += len(query_tokens & trigger_tokens) * 5
    score += len(query_tokens & tags_tokens) * 4
    score += len(query_tokens & answer_tokens) * 2

    normalized_query = _normalize(query)
    normalized_trigger = _normalize(trigger_text)
    normalized_answer = _normalize(answer_text)

    if normalized_query and normalized_trigger:
        if normalized_trigger in normalized_query:
            score += 8
        if normalized_query in normalized_trigger:
            score += 6

    if normalized_query and normalized_answer and normalized_query in normalized_answer:
        score += 4

    if entry.get("scope") == "both":
        score += 1

    return score


async def get_relevant_admin_knowledge(
    guild_id: int,
    query: str,
    *,
    is_ticket: bool,
    limit: int = 4,
) -> list[dict]:
    """Retorna entradas aprovadas mais relevantes para a pergunta."""
    query = (query or "").strip()
    if not guild_id or not query:
        return []

    scope = "ticket" if is_ticket else "public"
    entries = await db.get_admin_knowledge_entries(guild_id, scope=scope)
    if not entries:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[int, dict]] = []
    for entry in entries:
        score = _score_entry(entry, query, query_tokens)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda item: (item[0], item[1].get("id", 0)), reverse=True)
    return [entry for _, entry in scored[:max(1, limit)]]


def format_admin_knowledge_context(entries: list[dict]) -> str:
    """Formata entradas aprovadas para injecao no prompt."""
    if not entries:
        return ""

    lines = [
        "[=== CONHECIMENTO APROVADO POR ADMINS ===",
        "Prioridade alta: use estes itens antes de assumir algo com base em conversa aleatoria do servidor.",
        "Se um item abaixo responder diretamente a pergunta, siga-o.",
        "Se os itens nao cobrirem a pergunta, admita limite e nao invente informacao.",
    ]

    for index, entry in enumerate(entries, start=1):
        scope = entry.get("scope", "both")
        tags = (entry.get("tags") or "").strip()
        lines.append(f"{index}. Escopo aprovado: {scope}")
        lines.append(f"Gatilho/pergunta: {entry.get('trigger_text', '')}")
        lines.append(f"Resposta aprovada: {entry.get('answer_text', '')}")
        if tags:
            lines.append(f"Tags: {tags}")

    lines.append("=== FIM DO CONHECIMENTO APROVADO ===]")
    return "\n".join(lines)
