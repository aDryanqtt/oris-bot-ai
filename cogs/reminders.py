"""
Cog Lembretes — Sistema de lembretes com checagem periódica.
"""

import discord
from discord.ext import commands, tasks
import re
import logging
from datetime import timedelta

from utils.database import db
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from config import COLOR_INFO, now_br, format_datetime_br

logger = logging.getLogger(__name__)

async def send_error(bot, channel_id, title, erro_msg):
    werror = emoji("wCancel", "🛑")
    text = f"**{werror} {parse_emojis(title)}**\n\n{parse_emojis(erro_msg)}"
    await send_components(bot, channel_id, [container([section(text)])])

async def send_reminder_info(bot, channel_id, title, content, icon="wClock", fallback="⏰", footer=None, ping=None):
    wicon = emoji(icon, fallback)
    comps = [section(f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(content)[:4096]}")]
    if footer:
        comps.append(text_display(f"-# {parse_emojis(footer)}"))
    await send_components(bot, channel_id, [container(comps)], content=ping)


def parse_time(time_str: str) -> timedelta | None:
    """
    Converte string de tempo para timedelta.
    Suporta: 30s, 5m, 2h, 1d, combinações como 1h30m
    """
    pattern = re.compile(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?')
    match = pattern.fullmatch(time_str.strip().lower())

    if not match or not any(match.groups()):
        return None

    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)

    total = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    if total.total_seconds() < 30:
        return None  # Mínimo 30 segundos
    if total.total_seconds() > 604800:  # 7 dias
        return None

    return total


class RemindersCog(commands.Cog, name="⏰ Lembretes"):
    """Sistema de lembretes agendados."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Inicia o loop de verificação quando o cog carrega."""
        self.check_reminders.start()

    async def cog_unload(self):
        """Para o loop quando o cog descarrega."""
        self.check_reminders.cancel()

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        """Verifica lembretes pendentes a cada 30 segundos."""
        try:
            pending = await db.get_pending_reminders()

            for reminder in pending:
                try:
                    channel = self.bot.get_channel(reminder['channel_id'])
                    if channel:
                        mention = f"<@{reminder['user_id']}>"

                        text = f"**Lembrete Disparado:**\n{reminder['message']}"
                        walert = emoji("wAlert", "🔔")
                        comps = [container([
                            section(f"**{walert} Lembrete!**\n\n{parse_emojis(reminder['message'])}"),
                            text_display(f"-# ID do Lembrete: #{reminder['id']}")
                        ])]

                        # Envia e PINGA o user solto fora do embed simulando notificação real
                        await send_components(self.bot, channel.id, comps, content=mention)

                    await db.complete_reminder(reminder['id'])

                except Exception as e:
                    logger.error(f"Erro ao enviar lembrete #{reminder['id']}: {e}")
                    # Marca como completo mesmo com erro pra não ficar em loop infinito
                    await db.complete_reminder(reminder['id'])

        except Exception as e:
            logger.error(f"Erro no loop de lembretes: {e}")

    @check_reminders.before_loop
    async def before_check(self):
        """Espera o bot estar pronto antes de iniciar o loop."""
        await self.bot.wait_until_ready()

    @commands.command(name='lembrar')
    async def cmd_lembrar(self, ctx: commands.Context, tempo: str, *, mensagem: str):
        """⏰ Cria um lembrete. Uso: !lembrar <tempo> <mensagem>"""
        delta = parse_time(tempo)
        if delta is None:
            erro = "Use o formato: `30s`, `5m`, `2h`, `1d`, ou `1h30m`\n\n**Mínimo:** 30 segs\n**Máximo:** 7 dias"
            await send_error(self.bot, ctx.channel.id, "Tempo Inválido", erro)
            return

        remind_at = now_br() + delta
        guild_id = ctx.guild.id if ctx.guild else None

        reminder_id = await db.create_reminder(
            user_id=ctx.author.id,
            channel_id=ctx.channel.id,
            guild_id=guild_id,
            message=mensagem[:500],
            remind_at=remind_at.isoformat()
        )

        total_secs = int(delta.total_seconds())
        parts = []
        if total_secs >= 86400:
            parts.append(f"{total_secs // 86400} dia(s)")
            total_secs %= 86400
        if total_secs >= 3600:
            parts.append(f"{total_secs // 3600} hora(s)")
            total_secs %= 3600
        if total_secs >= 60:
            parts.append(f"{total_secs // 60} minuto(s)")
            total_secs %= 60
        if total_secs > 0:
            parts.append(f"{total_secs} segundo(s)")

        tempo_legivel = " e ".join(parts)

        content = (
            f"Tudo certo, {ctx.author.mention}! Vou te lembrar em **{tempo_legivel}**.\n\n"
            f"📝 **Anotado:**\n`{mensagem[:500]}`\n\n"
            f"⏰ **Agendado para:** `{format_datetime_br(remind_at)}`"
        )
        await send_reminder_info(
            self.bot, ctx.channel.id, "Lembrete Criado", content, "wClock", "⏰",
            f"Lembrete #{reminder_id} • Use !lembretes para ver todos"
        )

    @commands.command(name='lembretes')
    async def cmd_lembretes(self, ctx: commands.Context):
        """📋 Lista seus lembretes ativos."""
        reminders = await db.get_user_reminders(ctx.author.id)

        if not reminders:
            await send_reminder_info(
                self.bot, ctx.channel.id, "Lembretes Pessoais", 
                "Você não listou nenhum lembrete ativo no seu sistema da matriz.\n"
                "Use `!lembrar <tempo> <mensagem>` para criar um novo alarme.",
                "wList", "📋"
            )
            return

        lines = [f"**{emoji('wList', '📋')} Seus Lembretes ({len(reminders)})**\n"]
        for r in reminders[:10]:
            from datetime import datetime as dt
            remind_time = dt.fromisoformat(r['remind_at'])
            lines.append(f"• **#{r['id']}** • `{format_datetime_br(remind_time)}`\n└ `{r['message'][:100]}`")

        rodape = f"Mostrando 10 de {len(reminders)} alarmes. " if len(reminders) > 10 else "Nuvem de lembretes sincronizada. "
        rodape += "• !cancelarlembrete <id>"
        
        comps = [container([section("\n".join(lines)), text_display(f"-# {rodape}")])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='cancelarlembrete')
    async def cmd_cancelar_lembrete(self, ctx: commands.Context, reminder_id: int):
        """❌ Cancela um lembrete. Uso: !cancelarlembrete <id>"""
        sucesso = await db.cancel_reminder(reminder_id, ctx.author.id)

        if sucesso:
            await send_reminder_info(self.bot, ctx.channel.id, "Lembrete Cancelado", f"Seu lembrete agendado **#{reminder_id}** foi apagado da nuvem com sucesso.", "wCheck", "✅")
        else:
            await send_error(self.bot, ctx.channel.id, "Operação Recusada", f"Lembrete **#{reminder_id}** não foi encontrado atrelado à sua ID na matriz.")


async def setup(bot: commands.Bot):
    await bot.add_cog(RemindersCog(bot))
