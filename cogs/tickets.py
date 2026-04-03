"""
Cog Tickets - gerenciamento de boas-vindas, status, transcrição e handoff.
"""

import asyncio
import io
import logging
import re

import discord
from discord.ext import commands

from config import TIMEZONE_BR, format_datetime_br, now_br
from utils.containers import container, section, text_display, send_components, e as emoji
from utils.database import db
from utils.permissions import admin_only
from utils.ticketing import STAFF_ROLE_ID, is_ticket_channel, is_ticket_name

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_MESSAGES = 250


class TicketsCog(commands.Cog, name="🎫 Tickets"):
    """Integracao automatica com canais de atendimento e suporte."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _ticket_header(self, title: str, body: str) -> list:
        """Monta um painel visual simples para respostas de ticket."""
        ticket_icon = emoji("wTicket", "🎫")
        text = f"**{ticket_icon} {title}**\n\n{body}"
        return [container([section(text)])]

    async def _ensure_ticket_channel(self, ctx: commands.Context) -> bool:
        """Valida se o comando esta sendo usado em um canal de ticket reconhecido."""
        channel = ctx.channel
        if is_ticket_channel(channel) or await db.is_channel_ignored(channel.id):
            return True

        await send_components(
            self.bot,
            channel.id,
            self._ticket_header(
                "Canal invalido",
                "Esse comando so funciona em canais de ticket reconhecidos. Use-o dentro de um ticket ativo.",
            ),
        )
        return False

    async def _set_ticket_topic(self, channel: discord.TextChannel, state: str, actor, reason: str | None = None):
        """Marca o estado do ticket no topico do canal sem apagar o topico antigo."""
        actor_name = getattr(actor, "display_name", getattr(actor, "name", "Desconhecido"))
        parts = [
            f"[Oris Ticket] {state}",
            f"Por: {actor_name}",
            f"Em: {format_datetime_br(now_br())}",
        ]
        if reason:
            parts.append(f"Motivo: {reason}")
        if channel.topic:
            parts.append(f"Topico anterior: {channel.topic}")

        new_topic = " | ".join(parts)[:1024]
        try:
            await channel.edit(topic=new_topic, reason=f"Ticket marcado como {state.lower()}")
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning(f"Nao foi possivel atualizar o topico do ticket #{channel.name}: {exc}")

    async def _collect_ticket_snapshot(self, channel: discord.TextChannel, limit: int = 60):
        """Coleta um resumo rapido do ticket para o comando de status."""
        first_human = None
        last_message = None
        total = 0

        async for message in channel.history(limit=limit, oldest_first=True):
            total += 1
            last_message = message
            if first_human is None and not message.author.bot:
                first_human = message.author

        return first_human, last_message, total

    async def _build_transcript(self, channel: discord.TextChannel, limit: int) -> tuple[str, int]:
        """Gera o texto da transcricao do ticket."""
        limit = max(25, min(limit, MAX_TRANSCRIPT_MESSAGES))
        lines: list[str] = [
            f"Transcricao do ticket: #{channel.name}",
            f"Canal ID: {channel.id}",
            f"Servidor: {channel.guild.name}",
            f"Categoria: {channel.category.name if channel.category else 'Sem categoria'}",
            f"Criado em: {format_datetime_br(channel.created_at.astimezone(TIMEZONE_BR))}",
            f"Gerado em: {format_datetime_br(now_br())}",
            "",
            "-" * 96,
        ]

        count = 0
        async for message in channel.history(limit=limit, oldest_first=True):
            count += 1
            timestamp = format_datetime_br(message.created_at.astimezone(TIMEZONE_BR))
            author_name = getattr(message.author, "display_name", getattr(message.author, "name", "Desconhecido"))
            author_id = getattr(message.author, "id", "n/a")
            content = message.clean_content or message.content or "[mensagem sem texto]"

            if message.attachments:
                attachment_urls = ", ".join(att.url for att in message.attachments)
                content = f"{content}\n[Anexos] {attachment_urls}"

            if message.embeds:
                content = f"{content}\n[Embeds] {len(message.embeds)} embed(s)"

            lines.append(f"[{timestamp}] {author_name} ({author_id}): {content}")

        return "\n".join(lines).strip() + "\n", count

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Dispara toda vez que um canal e criado no servidor Discord."""
        if not isinstance(channel, discord.TextChannel):
            return

        if not is_ticket_name(channel.name):
            return

        # Aguarda uns segundos para permitir que o bot-mae de ticket envie a mensagem padrao primeiro.
        await asyncio.sleep(5)

        logger.info(f"🎫 Novo ticket detectado: #{channel.name} — Enviando saudacao inicial.")

        walert = emoji("wAlert", "👋")
        text = (
            f"**{walert} Boas-vindas a Oris Cloud!**\n\n"
            f"Estou aqui para agilizar seu atendimento e posso te ajudar independentemente.\n\n"
            f"Por favor, **diga com detalhes o que voce precisa** (comprar uma maquina, tirar duvidas, relatar um problema) para que eu comece.\n\n"
        )
        rodape = "-# Se for assunto financeiro ou de estorno, sinta-se livre para pedir suporte humano a qualquer momento."

        try:
            await send_components(self.bot, channel.id, [container([section(text), text_display(rodape)])])
        except Exception as e:
            logger.error(f"Erro ao ligar IA pro ticket {channel.name}: {e}")

    @commands.group(name="ticket", aliases=["tickets"], invoke_without_command=True)
    @admin_only()
    async def cmd_ticket(self, ctx: commands.Context):
        """Central de comandos para gestao de tickets."""
        lines = [
            f"`{ctx.prefix}ticket status` - Mostra o estado atual do canal.",
            f"`{ctx.prefix}ticket assumir` - Pausa a IA e marca o ticket como em atendimento.",
            f"`{ctx.prefix}ticket liberar` - Reativa a IA no canal.",
            f"`{ctx.prefix}ticket fechar [motivo]` - Marca o ticket como encerrado.",
            f"`{ctx.prefix}ticket transcript [limite]` - Gera uma transcricao em arquivo.",
        ]
        await send_components(
            self.bot,
            ctx.channel.id,
            self._ticket_header(
                "Funcoes de Ticket",
                "Use os subcomandos abaixo para gerenciar o atendimento humano e o historico do canal.\n\n"
                + "\n".join(f"• {line}" for line in lines),
            ),
        )

    @cmd_ticket.command(name="status", aliases=["info"])
    @admin_only()
    async def cmd_ticket_status(self, ctx: commands.Context):
        """Mostra o estado atual do ticket."""
        if not await self._ensure_ticket_channel(ctx):
            return

        channel = ctx.channel
        ignored = await db.is_channel_ignored(channel.id)
        active = is_ticket_name(channel.name) and not ignored
        try:
            first_human, last_message, total = await self._collect_ticket_snapshot(channel)
        except discord.Forbidden:
            first_human, last_message, total = None, None, 0

        status_icon = emoji("wFix2", "✅") if active else emoji("wLocked", "🔒")
        state_text = "Ativo" if active else "Pausado / encerrado"
        topic = channel.topic or "Sem topico"

        text = (
            f"**{status_icon} Status do Ticket**\n\n"
            f"• **Canal:** `#{channel.name}`\n"
            f"• **ID:** `{channel.id}`\n"
            f"• **Criado em:** `{format_datetime_br(channel.created_at.astimezone(TIMEZONE_BR))}`\n"
            f"• **Estado:** **{state_text}**\n"
            f"• **IA:** {'Respondendo normalmente' if active else 'Pausada'}\n"
            f"• **Solicitante provavel:** {getattr(first_human, 'mention', 'Nao identificado')}\n"
            f"• **Mensagens inspecionadas:** `{total}`\n"
            f"• **Ultima atividade:** {format_datetime_br(last_message.created_at.astimezone(TIMEZONE_BR)) if last_message else 'Sem historico'}\n"
            f"• **Categoria:** `{channel.category.name if channel.category else 'Sem categoria'}`\n"
            f"• **Topico:** `{topic[:300]}`"
        )
        await send_components(self.bot, ctx.channel.id, self._ticket_header("Resumo do Ticket", text))

    @cmd_ticket.command(name="assumir", aliases=["claim"])
    @admin_only()
    async def cmd_ticket_assumir(self, ctx: commands.Context, *, motivo: str = None):
        """Assume o ticket e pausa a IA."""
        if not await self._ensure_ticket_channel(ctx):
            return

        await db.ignore_channel(ctx.channel.id)
        await self._set_ticket_topic(ctx.channel, "EM ATENDIMENTO", ctx.author, motivo)

        text = (
            "A equipe humana assumiu este ticket e a IA foi pausada neste canal.\n\n"
            f"**Responsavel:** {ctx.author.mention}"
        )
        if motivo:
            text += f"\n**Motivo:** {motivo}"

        await send_components(
            self.bot,
            ctx.channel.id,
            self._ticket_header("Ticket Assumido", text),
            content=f"<@&{STAFF_ROLE_ID}>",
        )

    @cmd_ticket.command(name="liberar", aliases=["reabrir", "release"])
    @admin_only()
    async def cmd_ticket_liberar(self, ctx: commands.Context, *, motivo: str = None):
        """Reativa a IA no ticket."""
        if not await self._ensure_ticket_channel(ctx):
            return

        removed = await db.unignore_channel(ctx.channel.id)
        await self._set_ticket_topic(ctx.channel, "ABERTO", ctx.author, motivo)

        text = "A IA voltou a responder neste canal."
        if removed:
            text += "\nO canal foi removido da lista de tickets pausados."
        else:
            text += "\nEsse canal ja nao estava pausado."
        if motivo:
            text += f"\n**Motivo:** {motivo}"

        await send_components(self.bot, ctx.channel.id, self._ticket_header("Ticket Reaberto", text))

    @cmd_ticket.command(name="fechar", aliases=["close", "encerrar"])
    @admin_only()
    async def cmd_ticket_fechar(self, ctx: commands.Context, *, motivo: str = None):
        """Marca o ticket como fechado e pausa a IA."""
        if not await self._ensure_ticket_channel(ctx):
            return

        await db.ignore_channel(ctx.channel.id)
        await self._set_ticket_topic(ctx.channel, "FECHADO", ctx.author, motivo)

        text = (
            "O ticket foi marcado como encerrado e a IA foi pausada neste canal.\n\n"
            "Se for necessario reabrir, use o comando de liberacao."
        )
        if motivo:
            text += f"\n**Motivo:** {motivo}"

        await send_components(self.bot, ctx.channel.id, self._ticket_header("Ticket Encerrado", text))

    @cmd_ticket.command(name="transcript", aliases=["transcricao"])
    @admin_only()
    async def cmd_ticket_transcript(self, ctx: commands.Context, limite: int = 200):
        """Gera uma transcricao do ticket em arquivo."""
        if not await self._ensure_ticket_channel(ctx):
            return

        limite = max(25, min(limite, MAX_TRANSCRIPT_MESSAGES))

        async with ctx.channel.typing():
            try:
                transcript, total = await self._build_transcript(ctx.channel, limite)
            except discord.Forbidden:
                await send_components(
                    self.bot,
                    ctx.channel.id,
                    self._ticket_header(
                        "Falha na transcricao",
                        "Nao consegui ler o historico deste canal. Verifique se o bot tem permissao de `Ler Historico de Mensagens`.",
                    ),
                )
                return
            except Exception as exc:
                logger.error(f"Erro ao gerar transcricao do ticket #{ctx.channel.name}: {exc}", exc_info=exc)
                await send_components(
                    self.bot,
                    ctx.channel.id,
                    self._ticket_header(
                        "Falha na transcricao",
                        f"Ocorreu um erro inesperado ao gerar a transcricao: `{exc}`",
                    ),
                )
                return

            if total == 0:
                await send_components(
                    self.bot,
                    ctx.channel.id,
                    self._ticket_header(
                        "Sem historico",
                        "Nao encontrei mensagens visiveis para transcrever neste ticket.",
                    ),
                )
                return

            safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"ticket-{ctx.channel.id}-{ctx.channel.name}")
            file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"{safe_name}.txt")

            await ctx.send(
                content=(
                    f"**{emoji('wSave', '💾')} Transcricao gerada**\n\n"
                    f"Foram capturadas **{total} mensagens** nesta exportacao."
                ),
                file=file,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
