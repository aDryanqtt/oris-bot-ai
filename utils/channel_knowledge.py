"""
Channel Knowledge Cache — Varre canais configurados e mantém conteúdo em memória.
A IA usa esse conteúdo como contexto quando responde fora de tickets.
"""

import logging
import asyncio
from datetime import datetime, timedelta

import discord

logger = logging.getLogger(__name__)

# Cache global: { guild_id: {"content": str, "updated_at": datetime} }
_cache: dict[int, dict] = {}

# Tempo de expiração do cache (30 minutos)
CACHE_TTL_MINUTES = 30

# Máximo de caracteres por canal no contexto da IA
MAX_CHARS_PER_CHANNEL = 2000

# Máximo de mensagens por canal a varrer
MAX_MESSAGES_PER_CHANNEL = 50


async def refresh_guild(bot: discord.Client, guild_id: int) -> int:
    """
    Varre todos os canais configurados de um servidor e atualiza o cache.
    Retorna a quantidade de canais varridos com sucesso.
    """
    from utils.database import db

    scan_channels = await db.get_scan_channels(guild_id)
    if not scan_channels:
        _cache[guild_id] = {"content": "", "updated_at": datetime.now()}
        return 0

    sections = []
    success_count = 0

    for row in scan_channels:
        channel_id = row["channel_id"]
        label = row["label"] or str(channel_id)

        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"⚠️ Canal {channel_id} não encontrado ou inacessível.")
            continue

        try:
            lines = []
            async for msg in channel.history(limit=MAX_MESSAGES_PER_CHANNEL, oldest_first=True):
                if msg.author.bot:
                    continue
                if not msg.content:
                    continue
                content = msg.content.replace("\n", " ").strip()
                if content:
                    lines.append(content)

            if lines:
                full_text = "\n".join(lines)
                # Trunca para não estourar o contexto
                if len(full_text) > MAX_CHARS_PER_CHANNEL:
                    full_text = full_text[:MAX_CHARS_PER_CHANNEL] + "..."

                sections.append(f"📌 #{label} (canal do servidor):\n{full_text}")
                success_count += 1
                logger.info(f"✅ Canal '#{label}' varrido: {len(lines)} mensagens cacheadas.")

        except discord.Forbidden:
            logger.warning(f"🚫 Sem permissão para ler #{label} ({channel_id}).")
        except Exception as e:
            logger.error(f"❌ Erro ao varrer #{label}: {e}")

    combined = "\n\n".join(sections)
    _cache[guild_id] = {"content": combined, "updated_at": datetime.now()}
    logger.info(f"🔄 Cache do servidor {guild_id} atualizado. {success_count} canais varridos.")
    return success_count


async def refresh_all(bot: discord.Client):
    """Varre todos os servidores que têm canais configurados."""
    from utils.database import db
    guild_ids = await db.get_all_scan_guild_ids()
    for guild_id in guild_ids:
        try:
            await refresh_guild(bot, guild_id)
        except Exception as e:
            logger.error(f"Erro ao atualizar cache do guild {guild_id}: {e}")


def get_context(guild_id: int) -> str:
    """
    Retorna o contexto cacheado de um servidor.
    Se o cache estiver vazio ou expirado, retorna string vazia
    (o refresh acontece em background ou via comando).
    """
    entry = _cache.get(guild_id)
    if not entry or not entry["content"]:
        return ""

    # Verifica se o cache ainda é válido
    age = datetime.now() - entry["updated_at"]
    if age > timedelta(minutes=CACHE_TTL_MINUTES):
        return ""  # Expirado — será reconstruído em background

    return entry["content"]


def is_cache_fresh(guild_id: int) -> bool:
    """Verifica se o cache do servidor ainda é válido."""
    entry = _cache.get(guild_id)
    if not entry:
        return False
    age = datetime.now() - entry["updated_at"]
    return age <= timedelta(minutes=CACHE_TTL_MINUTES)


def get_cache_age(guild_id: int) -> str:
    """Retorna idade do cache formatada para exibição."""
    entry = _cache.get(guild_id)
    if not entry:
        return "nunca atualizado"
    age = datetime.now() - entry["updated_at"]
    minutes = int(age.total_seconds() // 60)
    if minutes < 1:
        return "agora mesmo"
    elif minutes == 1:
        return "1 minuto atrás"
    else:
        return f"{minutes} minutos atrás"
