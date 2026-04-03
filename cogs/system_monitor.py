"""
Cog System Monitor - status do bot, IA, logs e operacao.
Comandos sensiveis sao admin-only.
"""

import logging
import os
import time
from collections import deque

import discord
from discord.ext import commands

from utils.ollama_client import ollama
from utils.permissions import admin_only
from utils.database import db
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from config import now_br

logger = logging.getLogger(__name__)


async def send_admin_msg(bot, channel_id, title, msg, is_error=False, icon=None, fallback=""):
    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "X") if is_error else emoji("wCheck", "OK"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class SystemMonitorCog(commands.Cog, name="System Monitor"):
    """Monitoramento do sistema de IA e do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = now_br()
        self.total_requests = 0
        self.total_errors = 0
        self.log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot_debug.log")

    def _format_uptime(self) -> str:
        total_seconds = int((now_br() - self.start_time).total_seconds())
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s"

    def _tail_log_lines(self, limit: int = 20, level_filter: str | None = None) -> list[str]:
        """Le as ultimas linhas do log local, com filtro opcional."""
        if not os.path.exists(self.log_path):
            return []

        limit = max(1, min(limit, 80))
        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
            if level_filter:
                token = f"[{level_filter.upper()}]"
                matches = [line.rstrip() for line in f if token in line]
                return matches[-limit:]
            return [line.rstrip() for line in deque(f, maxlen=limit)]

    async def _get_ticket_snapshot(self, guild: discord.Guild | None, limit: int = 10) -> list[str]:
        """Resolve IDs de tickets pausados para nomes de canal legiveis."""
        channel_ids = await db.get_ignored_channel_ids(limit)
        if not channel_ids:
            return []

        rows = []
        for channel_id in channel_ids:
            channel = self.bot.get_channel(channel_id)
            if guild and channel and getattr(channel, "guild", None) and channel.guild.id != guild.id:
                continue
            if channel:
                guild_name = getattr(getattr(channel, "guild", None), "name", "DM")
                rows.append(f"`#{channel.name}` (`{channel.id}`) - {guild_name}")
            else:
                rows.append(f"`{channel_id}` - canal nao encontrado no cache")
            if len(rows) >= limit:
                break
        return rows

    @commands.command(name="status")
    async def cmd_status(self, ctx: commands.Context):
        """Dashboard completo do bot."""
        ollama_online = await ollama.is_online()
        provider_name = "Mistral API" if ollama.provider == "mistral" else "Ollama Local"
        stats = await db.get_bot_stats()

        walert = emoji("wAlert", "!")
        wcloud = emoji("wCloud", "Cloud")
        wpy = emoji("wPy", "AI")
        wshield = emoji("wShield", "Shield")
        wstatus = "ONLINE" if ollama_online else "OFFLINE"

        avatar_url = str(self.bot.user.display_avatar.url)
        text = (
            f"**{walert} Dashboard - {self.bot.user.name}**\n\n"
            f"**{wcloud} Servidor Host**\n"
            f"- Uptime da sessao: `{self._format_uptime()}`\n"
            f"- Conectado em: `{len(self.bot.guilds)} servidores`\n"
            f"- Latencia de Gateway: `{round(self.bot.latency * 1000)}ms`\n\n"
            f"**{wpy} Motor de IA**\n"
            f"- Provider ativo: `{provider_name}`\n"
            f"- Status de conexao: `{wstatus}`\n"
            f"- Modelo carregado: `{ollama.model}`\n"
            f"- Requisicoes na sessao: `{self.total_requests}` | Falhas: `{self.total_errors}`\n\n"
            f"**{wshield} Sistema & Banco**\n"
            f"- Modulos carregados: `{len(self.bot.cogs)}` | Comandos ativos: `{len(self.bot.commands)}`\n"
            f"- Usuarios sincronizados: `{stats['total_users']}` | Total de mensagens lidas: `{stats['total_messages']:,}`"
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text, avatar_url)])])

    @commands.command(name="healthcheck", aliases=["saude", "health"])
    @admin_only()
    async def cmd_healthcheck(self, ctx: commands.Context):
        """Resumo operacional do bot, IA, banco e tickets pausados."""
        ollama_online = await ollama.is_online()
        stats = await db.get_bot_stats()
        ignored_count = await db.count_ignored_channels()
        scan_channels = await db.get_scan_channels(ctx.guild.id) if ctx.guild else []
        log_channel_id = await db.get_bot_config("log_channel")
        recent_errors = self._tail_log_lines(limit=3, level_filter="ERROR")
        db_ok = getattr(db, "_db", None) is not None

        text = (
            f"**{emoji('wShield', 'Shield')} Healthcheck Operacional**\n\n"
            f"**Core**\n"
            f"- Sessao ativa: `{self._format_uptime()}`\n"
            f"- Gateway Discord: `{'OK' if not self.bot.is_closed() else 'FECHADO'}`\n"
            f"- Latencia: `{round(self.bot.latency * 1000)}ms`\n"
            f"- Banco SQLite: `{'OK' if db_ok else 'OFFLINE'}`\n\n"
            f"**IA**\n"
            f"- Provider: `{ollama.provider}`\n"
            f"- Modelo: `{ollama.model}`\n"
            f"- Status: `{'ONLINE' if ollama_online else 'OFFLINE'}`\n\n"
            f"**Operacao**\n"
            f"- Usuarios registrados: `{stats['total_users']}`\n"
            f"- Conversas salvas: `{stats['total_conversations']}`\n"
            f"- Comandos logados: `{stats['total_commands']}`\n"
            f"- Tickets pausados: `{ignored_count}`\n"
            f"- Canais de varredura neste servidor: `{len(scan_channels)}`\n"
            f"- Canal de log: `{log_channel_id or 'nao configurado'}`"
        )
        footer = "-# Ultimo erro relevante: " + (recent_errors[-1][:180] if recent_errors else "nenhum erro recente")
        await send_components(self.bot, ctx.channel.id, [container([section(text), text_display(footer)])])

    @commands.command(name="ultimoserros", aliases=["errosrecentes"])
    @admin_only()
    async def cmd_ultimos_erros(self, ctx: commands.Context, limite: int = 5):
        """Mostra as ultimas linhas de erro do bot_debug.log."""
        lines = self._tail_log_lines(limit=max(1, min(limite, 12)), level_filter="ERROR")
        if not lines:
            await send_admin_msg(self.bot, ctx.channel.id, "Sem erros recentes", "Nao encontrei entradas ERROR no arquivo bot_debug.log.")
            return

        text = (
            f"**{emoji('wAlert', '!')} Ultimos erros do bot**\n\n"
            + "\n".join(f"- `{line[:350]}`" for line in lines)
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name="logsbot", aliases=["logtail"])
    @admin_only()
    async def cmd_logs_bot(self, ctx: commands.Context, limite: int = 15):
        """Mostra as ultimas linhas gerais do log do bot."""
        lines = self._tail_log_lines(limit=max(1, min(limite, 25)))
        if not lines:
            await send_admin_msg(self.bot, ctx.channel.id, "Log vazio", "Nao encontrei linhas no bot_debug.log.")
            return

        block = "\n".join(lines)
        if len(block) > 3500:
            block = block[-3500:]

        text = f"**{emoji('wList', 'LOG')} Tail do bot_debug.log**\n\n```log\n{block}\n```"
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name="ticketsmonitor", aliases=["ticketmonitor"])
    @admin_only()
    async def cmd_tickets_monitor(self, ctx: commands.Context, limite: int = 10):
        """Lista tickets pausados para a IA."""
        ignored_count = await db.count_ignored_channels()
        rows = await self._get_ticket_snapshot(ctx.guild, limit=max(1, min(limite, 15)))

        if ignored_count == 0 or not rows:
            await send_admin_msg(self.bot, ctx.channel.id, "Nenhum ticket pausado", "Nao ha tickets pausados para a IA neste momento.")
            return

        text = (
            f"**{emoji('wTicket', 'Ticket')} Tickets em monitoramento**\n\n"
            f"Total pausado para a IA: `{ignored_count}`\n\n"
            + "\n".join(f"- {row}" for row in rows)
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name="modelos")
    async def cmd_modelos(self, ctx: commands.Context):
        """Lista modelos disponiveis."""
        async with ctx.channel.typing():
            models = await ollama.list_models()
            if not models:
                await send_admin_msg(self.bot, ctx.channel.id, "Modelos inacessiveis", "Nao foi possivel listar os modelos disponiveis na API.", True)
                return

            provider_name = "Mistral API" if ollama.provider == "mistral" else "Ollama Local"
            wpy = emoji("wPy", "AI")
            lines = [f"**{wpy} Modelos - {provider_name}**\n"]

            for model in models:
                if ollama.provider == "mistral":
                    name = model.get("id", "Desconhecido")
                else:
                    name = model.get("name", "Desconhecido")
                is_current = "OK " if name == ollama.model else "- "
                lines.append(f"{is_current}`{name}`")

            lines.append(f"\n-# Modelo ativo na memoria: {ollama.model}")
            avatar_url = str(self.bot.user.display_avatar.url)
            await send_components(self.bot, ctx.channel.id, [container([section("\n".join(lines), avatar_url)])])

    @commands.command(name="trocarmodelo")
    @admin_only()
    async def cmd_trocar_modelo(self, ctx: commands.Context, modelo: str):
        """Troca o modelo de IA."""
        old_model = ollama.model
        ollama.set_model(modelo)
        text = (
            f"**{emoji('wFix2', 'OK')} Swap de Modelo**\n\n"
            f"O motor de inferencia foi trocado com sucesso.\n"
            f"- Anterior: `{old_model}`\n"
            f"- Novo ativo: `{modelo}`"
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name="provider")
    @admin_only()
    async def cmd_provider(self, ctx: commands.Context, provider: str = None):
        """Troca provedor de IA."""
        if provider is None or provider not in ("mistral", "ollama"):
            msg = (
                f"**Provider atual:** `{ollama.provider}`\n"
                f"**Modelo injetado:** `{ollama.model}`\n\n"
                f"Use `!provider mistral` ou `!provider ollama` para trocar."
            )
            await send_admin_msg(self.bot, ctx.channel.id, "Provedor Inteligente", msg, icon="wPy", fallback="AI")
            return

        old = ollama.provider
        ollama.set_provider(provider)
        msg = (
            f"Provider trocado com sucesso.\n\n"
            f"**Antigo:** `{old}`\n"
            f"**Novo:** `{provider}`\n"
            f"**Modelo atual:** `{ollama.model}`"
        )
        await send_admin_msg(self.bot, ctx.channel.id, "Provider substituido", msg, icon="wPy", fallback="AI")

    @commands.command(name="ping")
    async def cmd_ping(self, ctx: commands.Context):
        """Latencia do bot e da IA."""
        discord_latency = round(self.bot.latency * 1000)
        start = time.perf_counter()
        ai_online = await ollama.is_online()
        ai_latency = round((time.perf_counter() - start) * 1000)
        provider_name = "Mistral" if ollama.provider == "mistral" else "Ollama"
        status = "ONLINE" if ai_online else "OFFLINE"

        text = (
            f"**{emoji('wAlert', 'PING')} Ping & Status**\n\n"
            f"- WebSocket Discord: `{discord_latency}ms`\n"
            f"- API {provider_name}: `{status}` em `{ai_latency}ms`"
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name="benchmark")
    @admin_only()
    async def cmd_benchmark(self, ctx: commands.Context):
        """Testa velocidade de resposta do modelo."""
        loading = await ctx.send(f"**{emoji('wClock', 'TIME')} Teste de estresse iniciado...**")

        async with ctx.channel.typing():
            prompt = "Responda com exatamente uma frase: Ola, estou funcionando perfeitamente."
            start = time.perf_counter()
            _, erro = await ollama.generate_simple(prompt)
            time_simple = time.perf_counter() - start

            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Falha de benchmark", erro, True)
                await loading.delete()
                return

            prompt2 = "Liste 5 linguagens de programacao populares em 2024, uma por linha."
            start = time.perf_counter()
            resposta2, erro2 = await ollama.generate_simple(prompt2)
            time_complex = time.perf_counter() - start

            if erro2:
                await send_admin_msg(self.bot, ctx.channel.id, "Falha de benchmark", erro2, True)
                await loading.delete()
                return

            tokens_est = len((resposta2 or "").split()) * 1.3
            tokens_str = f"{(tokens_est / time_complex):.1f} un/s" if time_complex > 0 else "indisponivel"
            avg = (time_simple + time_complex) / 2

            if avg < 3:
                rating = "Excelente"
            elif avg < 8:
                rating = "Bom"
            elif avg < 15:
                rating = "Lento"
            else:
                rating = "Critico"

            text = (
                f"**{emoji('wFire', 'HOT')} Relatorio de Estresse**\n\n"
                f"**Metadados**\n"
                f"- Modelo avaliado: `{ollama.model}`\n"
                f"- Veredito: **{rating}**\n\n"
                f"**Tempos de resposta**\n"
                f"- Inferencia simples: `{time_simple:.2f}s`\n"
                f"- Inferencia complexa: `{time_complex:.2f}s`\n"
                f"- Estimativa TPS: `{tokens_str}`"
            )
            await loading.delete()
            await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name="setavatar")
    @admin_only()
    async def cmd_setavatar(self, ctx: commands.Context, url: str = None):
        """Muda a foto de perfil do bot."""
        if not url and not ctx.message.attachments:
            await send_admin_msg(self.bot, ctx.channel.id, "Upload invalido", "Anexe um arquivo ou forneca uma URL direta.", True)
            return

        target_url = url if url else ctx.message.attachments[0].url
        async with ctx.channel.typing():
            try:
                import aiohttp

                async with aiohttp.ClientSession() as session:
                    async with session.get(target_url) as resp:
                        if resp.status != 200:
                            await send_admin_msg(self.bot, ctx.channel.id, "Erro HTTP", "Nao consegui baixar a imagem.", True)
                            return
                        data = await resp.read()

                await self.bot.user.edit(avatar=data)
                await send_admin_msg(self.bot, ctx.channel.id, "Upload concluido", "Foto de perfil atualizada com sucesso.")
            except discord.HTTPException as exc:
                await send_admin_msg(self.bot, ctx.channel.id, "Erro HTTP", str(exc), True)
            except Exception as exc:
                await send_admin_msg(self.bot, ctx.channel.id, "Falha desconhecida", str(exc), True)

    @commands.command(name="setname")
    @admin_only()
    async def cmd_setname(self, ctx: commands.Context, *, nome: str):
        """Muda o nome do bot."""
        try:
            await self.bot.user.edit(username=nome)
            await send_admin_msg(self.bot, ctx.channel.id, "Renomeacao completa", f"Nome alterado para **{nome}**.")
        except discord.HTTPException as exc:
            await send_admin_msg(self.bot, ctx.channel.id, "Erro HTTP", str(exc), True)
        except Exception as exc:
            await send_admin_msg(self.bot, ctx.channel.id, "Excecao", str(exc), True)

    @commands.command(name="canalbot")
    @admin_only()
    async def cmd_canal_bot(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Define o unico canal onde o bot respondera a comandos."""
        if canal is None:
            await db.set_bot_channel(ctx.guild.id, None)
            await send_admin_msg(self.bot, ctx.channel.id, "Restricao limpa", "O bot voltou a responder em todos os canais permitidos.")
            return

        await db.set_bot_channel(ctx.guild.id, canal.id)
        await send_admin_msg(self.bot, ctx.channel.id, "Canal ancora registrado", f"Todos os comandos ficaram restritos a {canal.mention}.")

    @commands.command(name="criarcanal")
    @admin_only()
    async def cmd_criar_canal(self, ctx: commands.Context):
        """Cria um canal exclusivo para o bot e restringe os comandos a ele."""
        async with ctx.channel.typing():
            try:
                canal = await ctx.guild.create_text_channel("bot-comandos-oris")
                await db.set_bot_channel(ctx.guild.id, canal.id)
                await send_admin_msg(self.bot, ctx.channel.id, "Sala criada", f"Canal {canal.mention} criado e definido como ancora do bot.")
                msg = (
                    f"**{emoji('wHome', 'HOME')} Estacao de Comando Principal**\n\n"
                    f"Este canal foi configurado para comandos do bot. Use `{ctx.prefix}ajuda`."
                )
                await send_components(self.bot, canal.id, [container([section(msg)])])
            except discord.Forbidden:
                await send_admin_msg(self.bot, ctx.channel.id, "Bloqueio de privilegio", "Faltam permissoes para criar canal.", True)
            except Exception as exc:
                await send_admin_msg(self.bot, ctx.channel.id, "Excecao", str(exc), True)

    @commands.command(name="setlog")
    @admin_only()
    async def cmd_setlog(self, ctx: commands.Context, canal: discord.TextChannel = None):
        """Define o canal para monitoramento global de conversas com a IA."""
        if canal is None:
            await db.set_bot_config("log_channel", None)
            await send_admin_msg(self.bot, ctx.channel.id, "Radar desativado", "O espelho de logs globais foi removido.")
            return

        await db.set_bot_config("log_channel", str(canal.id))
        msg = (
            f"Canal de monitoramento definido para {canal.mention}.\n"
            f"A partir de agora, as conversas da IA serao replicadas nele."
        )
        await send_admin_msg(self.bot, ctx.channel.id, "Radar ativo", msg, icon="wShield", fallback="Shield")


async def setup(bot: commands.Bot):
    await bot.add_cog(SystemMonitorCog(bot))
