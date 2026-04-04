"""
Channel Knowledge Cache.
Varre canais configurados e guarda secoes em memoria para contexto da IA.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta

import discord

logger = logging.getLogger(__name__)

# Cache global: { guild_id: {"content": str, "sections": list[dict], "updated_at": datetime} }
_cache: dict[int, dict] = {}

CACHE_TTL_MINUTES = 30
MAX_CHARS_PER_CHANNEL = 2000
MAX_MESSAGES_PER_CHANNEL = 50

STOPWORDS = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "sobre", "que", "qual", "quais",
    "como", "quando", "onde", "isso", "isto", "essa", "esse", "e",
    "ou", "mas", "pra", "pro", "tem", "ta", "vai", "ser", "estar",
}


def _normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9_]{3,}", _normalize(text)))
    return {token for token in tokens if token not in STOPWORDS}


def _score_section(section: dict, query_tokens: set[str]) -> int:
    label_tokens = _tokenize(section.get("label", ""))
    content_tokens = _tokenize(section.get("content", ""))
    score = 0
    score += len(query_tokens & label_tokens) * 4
    score += len(query_tokens & content_tokens) * 2
    return score


async def refresh_guild(bot: discord.Client, guild_id: int) -> int:
    """
    Varre os canais configurados de um servidor e atualiza o cache.
    Retorna a quantidade de canais lidos com sucesso.
    """
    from utils.database import db

    scan_channels = await db.get_scan_channels(guild_id)
    if not scan_channels:
        _cache[guild_id] = {"content": "", "sections": [], "updated_at": datetime.now()}
        return 0

    sections: list[dict] = []
    success_count = 0

    for row in scan_channels:
        channel_id = row["channel_id"]
        label = row["label"] or str(channel_id)

        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning("Canal %s nao encontrado ou inacessivel.", channel_id)
            continue

        try:
            lines: list[str] = []
            async for msg in channel.history(limit=MAX_MESSAGES_PER_CHANNEL, oldest_first=True):
                if msg.author.bot or not msg.content:
                    continue

                content = msg.content.replace("\n", " ").strip()
                if content:
                    lines.append(content)

            if not lines:
                continue

            full_text = "\n".join(lines)
            if len(full_text) > MAX_CHARS_PER_CHANNEL:
                full_text = full_text[:MAX_CHARS_PER_CHANNEL] + "..."

            sections.append(
                {
                    "channel_id": channel_id,
                    "label": label,
                    "content": full_text,
                    "formatted": f"#{label} (canal do servidor):\n{full_text}",
                }
            )
            success_count += 1
            logger.info("Canal '#%s' varrido: %s mensagens cacheadas.", label, len(lines))

        except discord.Forbidden:
            logger.warning("Sem permissao para ler #%s (%s).", label, channel_id)
        except Exception as exc:
            logger.error("Erro ao varrer #%s: %s", label, exc)

    combined = "\n\n".join(f"📌 {section['formatted']}" for section in sections)
    _cache[guild_id] = {
        "content": combined,
        "sections": sections,
        "updated_at": datetime.now(),
    }
    logger.info("Cache do servidor %s atualizado. %s canais varridos.", guild_id, success_count)
    return success_count


async def refresh_all(bot: discord.Client):
    """Varre todos os servidores que tem canais configurados."""
    from utils.database import db

    guild_ids = await db.get_all_scan_guild_ids()
    for guild_id in guild_ids:
        try:
            await refresh_guild(bot, guild_id)
        except Exception as exc:
            logger.error("Erro ao atualizar cache do guild %s: %s", guild_id, exc)


def get_context(guild_id: int) -> str:
    """
    Retorna o contexto cacheado completo de um servidor.
    Se o cache estiver vazio ou expirado, retorna string vazia.
    """
    entry = _cache.get(guild_id)
    if not entry or not entry["content"]:
        return ""

    age = datetime.now() - entry["updated_at"]
    if age > timedelta(minutes=CACHE_TTL_MINUTES):
        return ""

    return entry["content"]


def get_relevant_context(guild_id: int, query: str, max_sections: int = 2) -> str:
    """Retorna apenas as secoes do cache mais relevantes para a pergunta."""
    entry = _cache.get(guild_id)
    if not entry or not entry.get("sections"):
        return ""

    age = datetime.now() - entry["updated_at"]
    if age > timedelta(minutes=CACHE_TTL_MINUTES):
        return ""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    scored: list[tuple[int, dict]] = []
    for section in entry["sections"]:
        score = _score_section(section, query_tokens)
        if score > 0:
            scored.append((score, section))

    if not scored:
        return ""

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [section for _, section in scored[:max(1, max_sections)]]
    return "\n\n".join(f"📌 {section['formatted']}" for section in selected)


def is_cache_fresh(guild_id: int) -> bool:
    """Verifica se o cache do servidor ainda e valido."""
    entry = _cache.get(guild_id)
    if not entry:
        return False

    age = datetime.now() - entry["updated_at"]
    return age <= timedelta(minutes=CACHE_TTL_MINUTES)


def get_cache_age(guild_id: int) -> str:
    """Retorna idade do cache formatada para exibicao."""
    entry = _cache.get(guild_id)
    if not entry:
        return "nunca atualizado"

    age = datetime.now() - entry["updated_at"]
    minutes = int(age.total_seconds() // 60)
    if minutes < 1:
        return "agora mesmo"
    if minutes == 1:
        return "1 minuto atras"
    return f"{minutes} minutos atras"
