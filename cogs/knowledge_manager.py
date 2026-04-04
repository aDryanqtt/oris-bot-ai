"""
Gestao de conhecimento aprovado por administradores.
Permite ensinar respostas validadas para a IA usar em tickets e fora deles.
"""

from __future__ import annotations

import unicodedata

import discord
from discord.ext import commands

from utils.admin_knowledge import get_relevant_admin_knowledge
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from utils.database import db
from utils.permissions import admin_only
from utils.ticketing import is_ticket_channel


def _normalize_scope(raw: str | None) -> str | None:
    text = (raw or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    mapping = {
        "publico": "public",
        "public": "public",
        "chat": "public",
        "geral": "public",
        "ticket": "ticket",
        "tickets": "ticket",
        "ambos": "both",
        "ambas": "both",
        "both": "both",
        "geral_eticket": "both",
    }
    return mapping.get(text)


def _scope_label(scope: str) -> str:
    return {
        "public": "publico",
        "ticket": "ticket",
        "both": "ambos",
    }.get(scope, scope)


def _parse_pipe_payload(payload: str, minimum_parts: int) -> list[str]:
    parts = [part.strip() for part in (payload or "").split("|")]
    parts = [part for part in parts if part]
    if len(parts) < minimum_parts:
        return []
    return parts


async def send_admin_msg(bot, channel_id: int, title: str, msg: str, is_error: bool = False, icon: str | None = None, fallback: str = ""):
    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "X") if is_error else emoji("wCheck", "OK"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class KnowledgeManagerCog(commands.Cog, name="Knowledge"):
    """Comandos para conhecimento aprovado da IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_referenced_message(self, ctx: commands.Context) -> discord.Message | None:
        reference = getattr(ctx.message, "reference", None)
        if not reference:
            return None

        resolved = getattr(reference, "resolved", None)
        if isinstance(resolved, discord.Message):
            return resolved

        message_id = getattr(reference, "message_id", None)
        if not message_id:
            return None

        try:
            return await ctx.channel.fetch_message(message_id)
        except Exception:
            return None

    @commands.group(name="conhecimento", aliases=["knowledge", "kb"], invoke_without_command=True)
    @admin_only()
    async def cmd_conhecimento(self, ctx: commands.Context):
        """Central de conhecimento aprovado por admins."""
        lines = [
            f"`{ctx.prefix}conhecimento adicionar <escopo> | <gatilho> | <resposta> | [tags]`",
            f"`{ctx.prefix}conhecimento responder <escopo> | <resposta> | [tags]`  (use em reply)",
            f"`{ctx.prefix}conhecimento listar [escopo] [limite]`",
            f"`{ctx.prefix}conhecimento testar <pergunta>`",
            f"`{ctx.prefix}conhecimento remover <id>`",
            "",
            "Escopos aceitos: `publico`, `ticket`, `ambos`.",
        ]
        await send_admin_msg(
            self.bot,
            ctx.channel.id,
            "Conhecimento aprovado",
            "\n".join(lines),
            icon="wPy",
            fallback="KB",
        )

    @cmd_conhecimento.command(name="adicionar", aliases=["add", "ensinar"])
    @admin_only()
    async def cmd_conhecimento_add(self, ctx: commands.Context, *, payload: str):
        """Adiciona uma entrada de conhecimento aprovada."""
        parts = _parse_pipe_payload(payload, minimum_parts=3)
        if not parts:
            await send_admin_msg(
                self.bot,
                ctx.channel.id,
                "Sintaxe invalida",
                f"Use: `{ctx.prefix}conhecimento adicionar <escopo> | <gatilho> | <resposta> | [tags]`",
                True,
            )
            return

        scope = _normalize_scope(parts[0])
        trigger_text = parts[1]
        answer_text = parts[2]
        tags = parts[3] if len(parts) >= 4 else ""

        if not scope:
            await send_admin_msg(self.bot, ctx.channel.id, "Escopo invalido", "Use `publico`, `ticket` ou `ambos`.", True)
            return
        if len(trigger_text) < 4 or len(answer_text) < 4:
            await send_admin_msg(self.bot, ctx.channel.id, "Conteudo curto", "Gatilho e resposta precisam ser mais descritivos.", True)
            return

        entry_id = await db.add_admin_knowledge(
            guild_id=ctx.guild.id,
            scope=scope,
            trigger_text=trigger_text,
            answer_text=answer_text,
            created_by=ctx.author.id,
            tags=tags,
            source_channel_id=ctx.channel.id,
        )

        msg = (
            f"Entrada `#{entry_id}` salva para escopo **{_scope_label(scope)}**.\n"
            f"**Gatilho:** {trigger_text[:180]}\n"
            f"**Resposta:** {answer_text[:220]}"
        )
        if tags:
            msg += f"\n**Tags:** {tags[:180]}"

        await send_admin_msg(self.bot, ctx.channel.id, "Conhecimento salvo", msg, icon="wCheck", fallback="OK")

    @cmd_conhecimento.command(name="responder", aliases=["reply", "capturar"])
    @admin_only()
    async def cmd_conhecimento_reply(self, ctx: commands.Context, *, payload: str):
        """Salva conhecimento usando a mensagem respondida como pergunta/gatilho."""
        referenced = await self._resolve_referenced_message(ctx)
        if not referenced or not (referenced.clean_content or referenced.content):
            await send_admin_msg(
                self.bot,
                ctx.channel.id,
                "Reply obrigatorio",
                "Responda a uma mensagem do usuario e execute o comando na mesma thread/canal.",
                True,
            )
            return

        parts = _parse_pipe_payload(payload, minimum_parts=2)
        if not parts:
            await send_admin_msg(
                self.bot,
                ctx.channel.id,
                "Sintaxe invalida",
                f"Use em reply: `{ctx.prefix}conhecimento responder <escopo> | <resposta> | [tags]`",
                True,
            )
            return

        scope = _normalize_scope(parts[0])
        answer_text = parts[1]
        tags = parts[2] if len(parts) >= 3 else ""

        if not scope:
            await send_admin_msg(self.bot, ctx.channel.id, "Escopo invalido", "Use `publico`, `ticket` ou `ambos`.", True)
            return

        trigger_text = (referenced.clean_content or referenced.content or "").strip()
        if len(trigger_text) < 4 or len(answer_text) < 4:
            await send_admin_msg(self.bot, ctx.channel.id, "Conteudo curto", "A mensagem respondida e a resposta precisam ser descritivas.", True)
            return

        entry_id = await db.add_admin_knowledge(
            guild_id=ctx.guild.id,
            scope=scope,
            trigger_text=trigger_text,
            answer_text=answer_text,
            created_by=ctx.author.id,
            tags=tags,
            source_channel_id=referenced.channel.id,
            source_message_id=referenced.id,
        )

        msg = (
            f"Aprendizado `#{entry_id}` salvo a partir da mensagem respondida.\n"
            f"**Pergunta/Gatilho:** {trigger_text[:180]}\n"
            f"**Resposta aprovada:** {answer_text[:220]}"
        )
        if tags:
            msg += f"\n**Tags:** {tags[:180]}"

        await send_admin_msg(self.bot, ctx.channel.id, "Conhecimento capturado", msg, icon="wPy", fallback="KB")

    @cmd_conhecimento.command(name="listar", aliases=["list"])
    @admin_only()
    async def cmd_conhecimento_list(self, ctx: commands.Context, escopo: str | None = None, limite: int = 10):
        """Lista entradas salvas de conhecimento aprovado."""
        scope = _normalize_scope(escopo) if escopo else None
        entries = await db.list_admin_knowledge(ctx.guild.id, limit=max(1, min(limite, 20)), scope=scope)

        if not entries:
            await send_admin_msg(self.bot, ctx.channel.id, "Sem entradas", "Nenhum conhecimento aprovado foi salvo ainda.", icon="wOff", fallback="...")
            return

        lines = ["**Base de conhecimento aprovada**\n"]
        for entry in entries:
            tags = f" | tags: {entry['tags']}" if entry.get("tags") else ""
            lines.append(
                f"`#{entry['id']}` [{_scope_label(entry['scope'])}] "
                f"{entry['trigger_text'][:90]}{tags}"
            )

        footer = "-# Use `conhecimento remover <id>` para excluir uma entrada."
        await send_components(self.bot, ctx.channel.id, [container([section("\n".join(lines)[:3800]), text_display(footer)])])

    @cmd_conhecimento.command(name="testar", aliases=["buscar", "match"])
    @admin_only()
    async def cmd_conhecimento_test(self, ctx: commands.Context, *, pergunta: str):
        """Mostra quais entradas seriam usadas para uma pergunta."""
        entries = await get_relevant_admin_knowledge(
            ctx.guild.id,
            pergunta,
            is_ticket=is_ticket_channel(ctx.channel),
            limit=5,
        )

        if not entries:
            await send_admin_msg(
                self.bot,
                ctx.channel.id,
                "Sem match",
                "Nao encontrei conhecimento aprovado relevante para essa pergunta.",
                icon="wSearch",
                fallback="?",
            )
            return

        lines = [f"**Matches para:** `{pergunta[:140]}`\n"]
        for entry in entries:
            tags = f"\nTags: {entry['tags']}" if entry.get("tags") else ""
            lines.append(
                f"`#{entry['id']}` [{_scope_label(entry['scope'])}] "
                f"{entry['trigger_text'][:120]}\n"
                f"Resposta: {entry['answer_text'][:200]}{tags}\n"
            )

        await send_components(
            self.bot,
            ctx.channel.id,
            [container([section("\n".join(lines)[:3900]), text_display("-# Preview do que a IA pode usar nesse contexto.")])],
        )

    @cmd_conhecimento.command(name="remover", aliases=["del", "delete", "apagar"])
    @admin_only()
    async def cmd_conhecimento_remove(self, ctx: commands.Context, entry_id: int):
        """Remove uma entrada de conhecimento aprovado."""
        removed = await db.remove_admin_knowledge(entry_id, ctx.guild.id)
        if not removed:
            await send_admin_msg(self.bot, ctx.channel.id, "ID nao encontrado", f"Nao achei a entrada `#{entry_id}` neste servidor.", True)
            return

        await send_admin_msg(self.bot, ctx.channel.id, "Conhecimento removido", f"A entrada `#{entry_id}` foi apagada da base aprovada.", icon="wCheck", fallback="OK")


async def setup(bot: commands.Bot):
    await bot.add_cog(KnowledgeManagerCog(bot))
