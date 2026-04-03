"""
Cog Moderação — Análise de sentimento, toxicidade, regras e avisos.
"""

import discord
from discord.ext import commands
import logging
import time

from utils.ollama_client import ollama
from utils.permissions import admin_only
from utils.database import db
from config import now_br

logger = logging.getLogger(__name__)

async def send_admin_msg(bot, channel_id, title, msg, is_error=False, icon=None, fallback=""):
    from utils.containers import container, section, send_components, e as emoji, parse_emojis
    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "🛑") if is_error else emoji("wCheck", "✅"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class ModerationCog(commands.Cog, name="🛡️ Moderação"):
    """Ferramentas de moderação inteligente com IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam_cache = {}

    async def _apply_punishment(self, member: discord.Member, guild: discord.Guild, reason: str, minutes: int):
        """Aplica warn e timeout ao usuário pelo AutoMod."""
        import datetime
        from utils.containers import container, section, e as emoji, parse_emojis
        try:
            duration = datetime.timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)
            
            await db.get_or_create_user(member.id, member.display_name)
            await db.add_warning(member.id, guild.id, self.bot.user.id, f"[AutoMod] {reason}")
            
            walert = emoji("wAlert", "⚠️")
            text = f"**{walert} Restrição Automática**\n\n**Motivo:** {parse_emojis(reason)}\n**Tempo de mute:** `{minutes} minutos`."
            
            try:
                from utils.containers import send_components
                await send_components(self.bot, member.id, [container([section(text)])])
            except:
                pass
                
        except discord.Forbidden:
            logger.error(f"AutoMod falhou: sem permissão para penalizar {member.display_name}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if message.author.guild_permissions.administrator:
            return

        if message.attachments:
            from utils.image_scanner import scan_attachment_nsfw
            for attachment in message.attachments:
                if await scan_attachment_nsfw(attachment):
                    await message.delete()
                    await self._apply_punishment(message.author, message.guild, "Imagem explicitamente proibida detectada.", 10)
                    return

        content_lower = message.content.lower()

        bad_words = ["porno", "nudes", "gore", "nazi", "racista", "nigger"]
        if any(word in content_lower for word in bad_words):
            await message.delete()
            await self._apply_punishment(message.author, message.guild, "Vocabulário proibido no chat.", 5)
            return

        if "discord.gg/" in content_lower or "discord.com/invite/" in content_lower:
            await message.delete()
            await self._apply_punishment(message.author, message.guild, "Divulgação de servidor proibida.", 5)
            return

        if len(message.mentions) > 4:
            await message.delete()
            await self._apply_punishment(message.author, message.guild, "Abuso de menções (Flood de ping).", 10)
            return

        user_id = message.author.id
        now = time.time()
        
        if user_id not in self.spam_cache:
            self.spam_cache[user_id] = []
            
        self.spam_cache[user_id] = [t for t in self.spam_cache[user_id] if now - t < 5.0]
        self.spam_cache[user_id].append(now)
        
        if len(self.spam_cache[user_id]) > 5:
            await message.delete()
            await self._apply_punishment(message.author, message.guild, "Flood de mensagens (Spam).", 5)
            self.spam_cache[user_id].clear()
            return

    @commands.command(name='analisar')
    async def cmd_analisar(self, ctx: commands.Context, *, texto: str):
        """📊 Analisa o sentimento de um texto. Uso: !analisar <texto>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis
        async with ctx.channel.typing():
            prompt = (
                f"Analise o sentimento do seguinte texto:\n\n\"{texto}\"\n\n"
                "Responda EXATAMENTE neste formato:\n"
                "**Sentimento:** [Positivo/Negativo/Neutro/Misto]\n"
                "**Confiança:** [Alta/Média/Baixa]\n"
                "**Emoções detectadas:** [lista de emoções]\n"
                "**Análise:** [breve explicação de 1-2 frases]"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Análise Falhou", erro, True)
            else:
                walert = emoji("wAlert", "📊")
                text = f"**{walert} Análise de Sentimento**\n\n{parse_emojis(resposta[:1800])}\n\n-# Texto: {texto[:200]}"
                comps = [container([section(text)])]
                await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='toxicidade')
    async def cmd_toxicidade(self, ctx: commands.Context, *, texto: str):
        """🛡️ Verifica se um texto é tóxico. Uso: !toxicidade <texto>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis
        async with ctx.channel.typing():
            prompt = (
                f"Analise a toxicidade do seguinte texto:\n\n\"{texto}\"\n\n"
                "Responda neste formato:\n"
                "**Nível de toxicidade:** [0-10]\n"
                "**Classificação:** [Seguro/Potencialmente ofensivo/Tóxico/Altamente tóxico]\n"
                "**Motivo:** [explicação breve]\n"
                "**Contém:** [spam/discurso de ódio/assédio/ameaça/conteúdo sexual/nenhum]"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Monitoramento de Risco Falhou", erro, True)
            else:
                wshield = emoji("wShield", "🛡️")
                text = f"**{wshield} Veredito de Toxicidade**\n\n{parse_emojis(resposta[:1800])}"
                comps = [container([section(text)])]
                await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='regras')
    async def cmd_regras(self, ctx: commands.Context):
        """📜 Mostra as regras do servidor."""
        from utils.containers import container, section, separator, text_display, send_components, e as emoji
        wshield = emoji("wShield", "🛡️")
        wlock = emoji("wLocked", "🔒")
        warrow = emoji("wArrow", "➡️")
        regras = [
            "**1️⃣ Respeito** — Trate todos com respeito. Sem insultos, assédio ou discriminação.",
            "**2️⃣ Sem Spam** — Não faça spam de mensagens, links ou menções.",
            "**3️⃣ Canais Corretos** — Use cada canal para seu propósito.",
            "**4️⃣ Sem NSFW** — Conteúdo adulto proibido em todos os canais.",
            "**5️⃣ Sem Pirataria** — Não compartilhe conteúdo pirata ou links ilegais.",
            "**6️⃣ Privacidade** — Não compartilhe dados pessoais de outros membros.",
            "**7️⃣ Bot** — Use os comandos do bot de forma responsável.",
            "**8️⃣ Português** — Comunique-se preferencialmente em português.",
        ]
        text = f"**{wshield} Regras do Servidor**\n\n" + "\n".join(regras)
        comps = [container([section(text), text_display(f"-# {wlock} Violações podem resultar em punição severa e banimento.")])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='reescrever')
    async def cmd_reescrever(self, ctx: commands.Context, *, texto: str):
        """✍️ Reescreve texto de forma mais profissional. Uso: !reescrever <texto>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis
        async with ctx.channel.typing():
            prompt = (
                f"Reescreva o seguinte texto de forma mais profissional, clara e educada, "
                f"mantendo a mesma mensagem:\n\n\"{texto}\"\n\nRetorne apenas o texto reescrito."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Erro no LLM", erro, True)
            else:
                wfix = emoji("wFix", "✍️")
                text = (
                    f"**{wfix} Texto Reescrito**\n\n"
                    f"{parse_emojis(resposta[:1500])}\n\n"
                    f"-# Original submetido: {texto[:200]}"
                )
                comps = [container([section(text)])]
                await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='warn')
    @admin_only()
    async def cmd_warn(self, ctx: commands.Context, membro: discord.Member, *, motivo: str):
        """⚠️ Dá um aviso a um membro. 🔒 Admin. Uso: !warn @user <motivo>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis
        if not ctx.guild:
            return
        await db.get_or_create_user(membro.id, membro.display_name)
        warn_id = await db.add_warning(membro.id, ctx.guild.id, ctx.author.id, motivo)
        warnings = await db.get_warnings(membro.id, ctx.guild.id)
        walert = emoji("wAlert", "⚠️")
        text = (
            f"**{walert} Aviso Administrativo Aplicado!**\n\n"
            f"• **Alvo Penalizado:** {membro.mention}\n"
            f"• **Motivo Documentado:** `{motivo}`\n"
            f"• **Juiz (Admin):** {ctx.author.mention}\n"
            f"• **Total de Strikes:** **{len(warnings)}** infração(ões)\n\n"
            f"-# Ticket de Advertência: #{warn_id}"
        )
        comps = [container([section(text)])]
        await send_components(self.bot, ctx.channel.id, comps)
        try:
            msg_dm = f"**{walert} Você tomou um Advertência (Warn) em {ctx.guild.name}!**\n\n**Motivo:** {parse_emojis(motivo)}\n**Total de Strikes:** {len(warnings)}"
            await send_components(self.bot, membro.id, [container([section(msg_dm)])])
        except Exception:
            pass

    @commands.command(name='avisos')
    @admin_only()
    async def cmd_avisos(self, ctx: commands.Context, membro: discord.Member):
        """📋 Lista avisos de um membro. 🔒 Admin. Uso: !avisos @user"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis
        if not ctx.guild:
            return
        warnings = await db.get_warnings(membro.id, ctx.guild.id)
        walert = emoji("wAlert", "⚠️")
        if not warnings:
            comps = [container([section(f"**{walert} Histórico Criminal — {membro.display_name}**\n\nA ficha deste usuário está totalmente limpa. ✅")])]
            await send_components(self.bot, ctx.channel.id, comps)
            return
            
        lines = [f"**{walert} Ficha Administrativa — {membro.display_name}** ({len(warnings)} infração(ões))\n"]
        for w in warnings[:10]:
            from datetime import datetime as dt
            try:
                ts = dt.fromisoformat(w['timestamp']).strftime("%d/%m/%Y %H:%M")
            except Exception:
                ts = "N/A"
            lines.append(f"• `#{w['id']}` `{ts}` — {parse_emojis(w['reason'][:150])}")
            
        comps = [container([section("\n".join(lines))])]
        await send_components(self.bot, ctx.channel.id, comps)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
