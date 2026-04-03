"""
Cog Channel Analyzer — Analisa canais do Discord por ID, lê histórico, busca mensagens.
Comandos de análise são admin-only.
"""

import discord
from discord.ext import commands
import logging
from datetime import timedelta

from utils.ollama_client import ollama
from utils.helpers import split_message, extract_urls, fetch_url_content
from utils.permissions import admin_only
from utils import channel_knowledge
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from config import CHANNEL_FETCH_LIMIT, COLOR_INFO, now_br

logger = logging.getLogger(__name__)

async def send_admin_msg(bot, channel_id, title, msg, is_error=False, icon=None, fallback=""):
    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "🛑") if is_error else emoji("wCheck", "✅"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class ChannelAnalyzerCog(commands.Cog, name="🔍 Channel Analyzer"):
    """Análise inteligente de canais do Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _fetch_channel_messages(self, channel: discord.TextChannel, limit: int = 50) -> list[dict]:
        """Busca mensagens de um canal e retorna dados estruturados."""
        messages_data = []
        try:
            async for msg in channel.history(limit=limit):
                messages_data.append({
                    "author": msg.author.display_name,
                    "content": msg.content[:500] if msg.content else "[mídia/embed]",
                    "timestamp": msg.created_at.strftime("%d/%m %H:%M"),
                    "has_attachments": len(msg.attachments) > 0,
                    "has_embeds": len(msg.embeds) > 0,
                    "reactions": sum(r.count for r in msg.reactions) if msg.reactions else 0,
                })
        except discord.Forbidden:
            return []
        except Exception as e:
            logger.error(f"Erro ao buscar mensagens: {e}")
            return []

        return messages_data

    def _format_messages_for_ai(self, messages: list[dict]) -> str:
        """Formata mensagens para contexto da IA."""
        if not messages:
            return "Nenhuma mensagem encontrada."

        lines = []
        for msg in reversed(messages):  # Mais antigas primeiro
            attachments = " [📎 Anexo]" if msg["has_attachments"] else ""
            reactions = f" [❤️ {msg['reactions']}]" if msg["reactions"] > 0 else ""
            lines.append(f"[{msg['timestamp']}] {msg['author']}: {msg['content']}{attachments}{reactions}")

        return '\n'.join(lines)

    @commands.command(name='analisarcanal')
    @admin_only()
    async def cmd_analisar_canal(self, ctx: commands.Context, canal: str = None, n: int = 50):
        """🔍 Analisa um canal. 🔒 Admin. Uso: !analisarcanal <#canal ou ID> [n_mensagens]"""
        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        n = min(n, CHANNEL_FETCH_LIMIT)
        loading = await ctx.send(f"🔍 Analisando **#{channel.name}** (últimas {n} mensagens)...")

        async with ctx.channel.typing():
            messages = await self._fetch_channel_messages(channel, limit=n)
            if not messages:
                await send_admin_msg(self.bot, ctx.channel.id, "Análise Falhou", "Não consegui acessar as mensagens deste canal.", True)
                await loading.delete()
                return

            formatted = self._format_messages_for_ai(messages)

            prompt = (
                f"Analise as seguintes mensagens do canal #{channel.name} de um servidor Discord:\n\n"
                f"{formatted}\n\n"
                "Forneça uma análise completa:\n"
                "1. **Resumo geral:** Do que o canal trata e o que foi discutido\n"
                "2. **Tópicos principais:** Lista dos assuntos mais discutidos\n"
                "3. **Usuários mais ativos:** Quem participou mais\n"
                "4. **Tom da conversa:** Formal, informal, técnico, etc.\n"
                "5. **Destaques:** Mensagens ou pontos mais importantes\n\n"
                "IMPORTANTE: Base sua análise APENAS nas mensagens fornecidas. NÃO invente informações."
            )

            resposta, erro = await ollama.generate_simple(prompt)
            await loading.delete()
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Falha na Análise", erro, True)
            else:
                stats = (
                    f"**{emoji('wList', '📊')} Tabela de Dados**\n"
                    f"• Interações varridas: `{len(messages)} mensagens`\n"
                    f"• Entidades (users): `{len(set(m['author'] for m in messages))}`\n"
                    f"• Pacotes binários (anexos): `{sum(1 for m in messages if m['has_attachments'])}`\n"
                    f"• Reações contadas: `{sum(m['reactions'] for m in messages)}`\n"
                )
                
                parts = split_message(resposta)
                for i, part in enumerate(parts):
                    header = f"**{emoji('wPy', '🔍')} Análise de Canal — {channel.name}**\n\n" if i == 0 else ""
                    text_block = f"{header}{part}"
                    if i == len(parts) - 1:
                        await send_components(self.bot, ctx.channel.id, [container([section(text_block), section(stats)])])
                    else:
                        await send_components(self.bot, ctx.channel.id, [container([section(text_block)])])

    @commands.command(name='buscarcanal')
    @admin_only()
    async def cmd_buscar_canal(self, ctx: commands.Context, canal: str, *, termo: str):
        """🔎 Busca mensagens em um canal. 🔒 Admin. Uso: !buscarcanal <#canal ou ID> <termo>"""
        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        loading = await ctx.send(f"🔎 Buscando `{termo}` em **#{channel.name}**...")

        async with ctx.channel.typing():
            found = []
            try:
                async for msg in channel.history(limit=200):
                    if termo.lower() in (msg.content or "").lower():
                        found.append({
                            "author": msg.author.display_name,
                            "content": msg.content[:300],
                            "timestamp": msg.created_at.strftime("%d/%m/%Y %H:%M"),
                            "jump_url": msg.jump_url,
                        })
                        if len(found) >= 20:
                            break
            except discord.Forbidden:
                await send_admin_msg(self.bot, ctx.channel.id, "Busca Negada", "Sem permissão de visão para ler o histórico deste canal.", True)
                await loading.delete()
                return

            await loading.delete()

            if not found:
                await send_admin_msg(self.bot, ctx.channel.id, "Busca sem Resultados", f"Nenhum frame contendo a chave de string `{termo}` foi detectado no #{channel.name}.", icon="wSearch", fallback="🔎")
                return

            lines = [f"**{emoji('wSearch', '🔎')} Pesquisa: \"{termo}\" em #{channel.name}**"]
            lines.append(f"A varredura obteve sucesso com **{len(found)}** entradas compatíveis.\n")

            for i, msg in enumerate(found[:10], 1):
                lines.append(f"**{i}. {msg['author']} — {msg['timestamp']}**\n`{msg['content'][:200]}`\n[🔗 Ir para Mensagem Original]({msg['jump_url']})\n")

            rodape = f"-# Mostrando 10 de {len(found)} resultados encontrados." if len(found) > 10 else f"-# Foram mostrados todos os {len(found)} resultados encontrados."
            comps = [container([section("\n".join(lines)), text_display(rodape)])]
            await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='resumircanal')
    @admin_only()
    async def cmd_resumir_canal(self, ctx: commands.Context, canal: str = None, n: int = 30):
        """📋 Resume as últimas mensagens de um canal. 🔒 Admin. Uso: !resumircanal <#canal ou ID> [n]"""
        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        n = min(n, CHANNEL_FETCH_LIMIT)

        async with ctx.channel.typing():
            messages = await self._fetch_channel_messages(channel, limit=n)
            if not messages:
                await send_admin_msg(self.bot, ctx.channel.id, "Resumo Negado", "Impossível acessar a tabela histórica no Discord.", True)
                return

            formatted = self._format_messages_for_ai(messages)

            prompt = (
                f"Resuma de forma concisa as últimas {len(messages)} mensagens do canal #{channel.name}:\n\n"
                f"{formatted}\n\n"
                "Faça um resumo executivo em tópicos:\n"
                "- O que foi discutido\n"
                "- Decisões tomadas (se houver)\n"
                "- Pendências/perguntas sem resposta\n\n"
                "BASEIE-SE APENAS nas mensagens fornecidas. NÃO invente nada."
            )

            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Erro do Motor de IA", erro, True)
            else:
                text = f"**{emoji('wList', '📋')} Ata de Reunião — #{channel.name}**\n\n{parse_emojis(resposta[:4096])}"
                rodape = f"-# Resumo extraído das últimas {len(messages)} mensagens deste canal."
                await send_components(self.bot, ctx.channel.id, [container([section(text), text_display(rodape)])])

    @commands.command(name='canais')
    async def cmd_canais(self, ctx: commands.Context):
        """📂 Lista todos os canais do servidor com IDs."""
        if not ctx.guild:
            await send_admin_msg(self.bot, ctx.channel.id, "Comando Isolado", "O mapeamento de canais exige o contexto de um Servidor Real.", True)
            return

        # Agrupa por categoria
        categories = {}
        for channel in ctx.guild.channels:
            if isinstance(channel, discord.TextChannel):
                cat_name = channel.category.name if channel.category else "Sem Categoria"
                if cat_name not in categories:
                    categories[cat_name] = []
                categories[cat_name].append(channel)

        lines = [f"**{emoji('wFolder', '📂')} Topologia de Redes — {ctx.guild.name}**\n"]
        for cat_name, channels in sorted(categories.items()):
            lines.append(f"**📁 {cat_name}**")
            for c in sorted(channels, key=lambda x: x.position):
                lines.append(f"• <#{c.id}> (`{c.id}`)")
            lines.append("")

        comps = [container([section("\n".join(lines)[:4000]), text_display("-# Use !analisarcanal <ID> para solicitar um audit a IA.")])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='lerlinks')
    @admin_only()
    async def cmd_ler_links(self, ctx: commands.Context, canal: str = None, n: int = 30):
        """🔗 Encontra e analisa links em um canal. 🔒 Admin. Uso: !lerlinks <#canal ou ID> [n]"""
        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        n = min(n, 100)
        loading = await ctx.send(f"🔗 Crawlando URLs brutas em **#{channel.name}**...")

        async with ctx.channel.typing():
            all_urls = []
            try:
                async for msg in channel.history(limit=n):
                    if msg.content:
                        urls = extract_urls(msg.content)
                        for url in urls:
                            all_urls.append({
                                "url": url,
                                "author": msg.author.display_name,
                                "timestamp": msg.created_at.strftime("%d/%m %H:%M"),
                            })
            except discord.Forbidden:
                await send_admin_msg(self.bot, ctx.channel.id, "Crawler Bloqueado", "Privilégios insuficientes pra escaneamento de URL neste canal.", True)
                await loading.delete()
                return
            await loading.delete()

            if not all_urls:
                await send_admin_msg(self.bot, ctx.channel.id, "Sem Links", f"Zero ponteiros externos localizados nas últimas {n} mensagens do canal.", icon="wCloud", fallback="☁️")
                return

            lines = [f"**{emoji('wLink', '🔗')} Crawl Result — #{channel.name}**\nDetecção positiva para **{len(all_urls)}** endpoints externos.\n"]

            for i, link_info in enumerate(all_urls[:15], 1):
                lines.append(f"**{i}. {link_info['author']} — {link_info['timestamp']}**\n`{link_info['url'][:200]}`\n")

            rodape = "-# Dica: Use `!link <url>` para que eu extraia e analise o código fonte HTML."
            await send_components(self.bot, ctx.channel.id, [container([section("\n".join(lines)[:4096]), text_display(rodape)])])

    @commands.command(name='atividade')
    @admin_only()
    async def cmd_atividade(self, ctx: commands.Context, canal: str = None, horas: int = 24):
        """📈 Mostra atividade recente de um canal. 🔒 Admin. Uso: !atividade <#canal> [horas]"""
        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        horas = min(horas, 168)  # Max 7 dias
        from datetime import datetime
        cutoff = datetime.utcnow() - timedelta(hours=horas)

        async with ctx.channel.typing():
            msg_count = 0
            authors = {}
            hour_activity = {}

            try:
                async for msg in channel.history(limit=500, after=cutoff):
                    msg_count += 1
                    author = msg.author.display_name
                    authors[author] = authors.get(author, 0) + 1
                    hour = msg.created_at.strftime("%H:00")
                    hour_activity[hour] = hour_activity.get(hour, 0) + 1
            except discord.Forbidden:
                await send_admin_msg(self.bot, ctx.channel.id, "Erro no Audit", "Visibilidade blindada. Eu não consigo ver canais privados ou ocultos para mim.", True)
                return

            if msg_count == 0:
                await send_admin_msg(self.bot, ctx.channel.id, "Zero de Tráfego", f"Atividade nula registrada na janela contígua de {horas} horas em #{channel.name}.", icon="wAlert", fallback="📉")
                return

            top_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5]
            authors_text = '\n'.join(f"• **{name}:** `{count} msgs`" for name, count in top_authors)
            peak_hour = max(hour_activity, key=hour_activity.get) if hour_activity else "N/A"

            text = (
                f"**{emoji('wActivity', '📈')} Tráfego Mensurado — #{channel.name}**\n\n"
                f"**Intervalo Auditado:** `Últimas {horas} horas`\n\n"
                f"**Métricas**\n"
                f"• Lotes trafegados: `{msg_count} mensagens`\n"
                f"• Nós únicos participando: `{len(authors)}`\n"
                f"• Janela de picos de stress: `{peak_hour}`\n\n"
                f"**🏆 Top Emissores**\n{authors_text}"
            )
            await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    async def _resolve_channel(self, ctx: commands.Context, canal_ref: str = None) -> discord.TextChannel:
        """Resolve referência de canal (menção, ID, ou nome) para um objeto TextChannel."""
        if canal_ref is None:
            if isinstance(ctx.channel, discord.TextChannel):
                return ctx.channel
            await send_admin_msg(self.bot, ctx.channel.id, "Resolução Falhou", "Especifique um canal válido: `!comando <#canal>` ou `!comando <ID>`", True)
            return None

        if canal_ref.startswith('<#') and canal_ref.endswith('>'):
            try:
                channel_id = int(canal_ref[2:-1])
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    return channel
            except ValueError:
                pass

        try:
            channel_id = int(canal_ref)
            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                return channel
        except ValueError:
            pass

        if ctx.guild:
            for ch in ctx.guild.text_channels:
                if ch.name.lower() == canal_ref.lower().strip('#'):
                    return ch

        await send_admin_msg(
            self.bot, ctx.channel.id, "String de Canal Desconhecida", 
            f"O canal requerido `{canal_ref}` não pôde ser instanciado via GetChannel.\n\n"
            "Métodos de injeção suportados:\n• Menção `<#ID>`\n• Snowflake numérico puro\n• Literal Name `geral`\n\nUse !canais para auditar o cache.", True)
        return None

    # ==================== SCAN CHANNELS ====================

    async def cog_load(self):
        import asyncio
        asyncio.create_task(self._auto_refresh_loop())

    async def _auto_refresh_loop(self):
        import asyncio
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await channel_knowledge.refresh_all(self.bot)
            except Exception as e:
                logger.error(f"Erro no auto-refresh do channel knowledge: {e}")
            await asyncio.sleep(30 * 60)

    @commands.command(name='scanadd')
    @admin_only()
    async def cmd_scan_add(self, ctx: commands.Context, canal: str = None):
        """📡 Adiciona canal à varredura de conhecimento da IA. 🔒 Admin. Uso: !scanadd <#canal>"""
        if not canal:
            await send_admin_msg(self.bot, ctx.channel.id, "Sintaxe Rejeitada", "Passe um ponteiro de canal válido. Exemplo: `!scanadd #canal`", True)
            return

        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        if not ctx.guild:
            await send_admin_msg(self.bot, ctx.channel.id, "Ambiente Bloqueado", "Scanner foi desenhado para Operações de Guild Server.", True)
            return

        from utils.database import db
        added = await db.add_scan_channel(channel.id, ctx.guild.id, channel.name)

        if not added:
            await send_admin_msg(self.bot, ctx.channel.id, "Redundant Request", f"#{channel.name} já obedece protocolo de scanner contínuo na memória.", icon="wShield", fallback="🛡️")
            return

        await ctx.send(f"📡 Vinculado. Disparando crawling em background na rota **#{channel.name}**...")
        async with ctx.channel.typing():
            count = await channel_knowledge.refresh_guild(self.bot, ctx.guild.id)

        msg = f"Canal de índice **#{channel.name}** foi plugado na matriz mestre da Inteligência.\nCanais que fornecem contexto ativo atualizados para `{count}` hosts."
        await send_admin_msg(self.bot, ctx.channel.id, "Crawling Set", msg, icon="wPy", fallback="🧠")

    @commands.command(name='scanremove')
    @admin_only()
    async def cmd_scan_remove(self, ctx: commands.Context, canal: str = None):
        """🗑️ Remove canal da varredura de conhecimento. 🔒 Admin. Uso: !scanremove <#canal>"""
        if not canal:
            await send_admin_msg(self.bot, ctx.channel.id, "Syntax Error", "Nenhum canal provido. Tente `!scanremove #canal`", True)
            return

        channel = await self._resolve_channel(ctx, canal)
        if not channel:
            return

        from utils.database import db
        removed = await db.remove_scan_channel(channel.id)

        if removed:
            if ctx.guild:
                await channel_knowledge.refresh_guild(self.bot, ctx.guild.id)
            await send_admin_msg(self.bot, ctx.channel.id, "Purged Base", f"A lixeira passou e removeu o **#{channel.name}** do seu aprendizado semântico.", icon="wCheck", fallback="🗑️")
        else:
            await send_admin_msg(self.bot, ctx.channel.id, "Cache Miss", f"O canal #{channel.name} já não constava nos registros ativos.", True)

    @commands.command(name='scanlist')
    @admin_only()
    async def cmd_scan_list(self, ctx: commands.Context):
        """📋 Lista canais monitorados pela IA. 🔒 Admin."""
        if not ctx.guild:
            await send_admin_msg(self.bot, ctx.channel.id, "Aviso DM", "Isso requer a visibilidade de uma hierarquia de servidor.", True)
            return

        from utils.database import db
        channels = await db.get_scan_channels(ctx.guild.id)

        if not channels:
            await send_admin_msg(self.bot, ctx.channel.id, "Cerebro Limpo", "Não há rotas sendo crawleadas pra injeção no modelo. Adicione com `!scanadd`.", icon="wOff", fallback="⭕")
            return

        fresh = channel_knowledge.is_cache_fresh(ctx.guild.id)
        age = channel_knowledge.get_cache_age(ctx.guild.id)

        lines = [f"**{emoji('wPy', '📡')} Base em Memória — Rotação de Contexto**\nDiferenciais passivos extraídos de instâncias TextChannels para IA.\n"]
        lines.append("**📁 Pontos de Rota ativados no Core:**")
        for ch in channels:
            canal_obj = self.bot.get_channel(ch['channel_id'])
            mention = f"<#{ch['channel_id']}>" if canal_obj else f"`#{ch['label']}`"
            lines.append(f"• {mention}")

        lines.append(f"\n**🔄 Validade do Snapshot:** {'✅ Integridade Alta' if fresh else '⚠️ Snapshot Degrada'} — _{age}_")
        lines.append(f"**📈 Total Injetado:** `{len(channels)} hosts mapeados`")

        rodape = "-# Caso precise revalidar, acione !scanrefresh manualmente na shell."
        await send_components(self.bot, ctx.channel.id, [container([section("\n".join(lines)[:4096]), text_display(rodape)])])

    @commands.command(name='scanrefresh')
    @admin_only()
    async def cmd_scan_refresh(self, ctx: commands.Context):
        """🔄 Força atualização do cache de todos os canais monitorados. 🔒 Admin."""
        if not ctx.guild:
            await send_admin_msg(self.bot, ctx.channel.id, "Guild Req", "Ambiente inadequado para Refresh de Servidor.", True)
            return

        loading = await ctx.send("🔄 Efetuando pull manual nas rotas atreladas à IA...")
        async with ctx.channel.typing():
            count = await channel_knowledge.refresh_guild(self.bot, ctx.guild.id)

        await loading.delete()
        if count == 0:
            await send_admin_msg(self.bot, ctx.channel.id, "Abortado", "Não há alvos registrados. Use `!scanadd` primeiro.")
        else:
            age = channel_knowledge.get_cache_age(ctx.guild.id)
            await send_admin_msg(self.bot, ctx.channel.id, "Commit Passos Finalizado", f"Tudo alinhado. `{count}` hosts foram puxados para o cache local.\nAge da pasta: {age}", icon="wSync", fallback="🔄")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelAnalyzerCog(bot))
