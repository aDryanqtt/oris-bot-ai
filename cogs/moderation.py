"""
Cog Moderacao - analise de sentimento, toxicidade, regras e avisos.
"""

import logging
import re
import time

import discord
from discord.ext import commands

from utils.database import db
from utils.ollama_client import ollama
from utils.permissions import admin_only
from utils.ticketing import is_staff_member

logger = logging.getLogger(__name__)

TEXT_RISK_TERMS = (
    "porno",
    "pornografia",
    "nudes",
    "gore",
    "nazi",
    "nazista",
    "racista",
    "racismo",
    "nigger",
)

AUTOMOD_TEXT_PROMPT = """Voce e um classificador de moderacao textual para Discord.
Analise a mensagem com contexto e intencao.

Regras obrigatorias:
- Nao marque violacao apenas porque existe uma palavra sensivel.
- Considere contexto inocente, citacao, explicacao, denuncia, critica, debate academico, leitura de regras e exemplos.
- Marque violacao somente se a mensagem realmente promover, atacar, assediar, ameacar ou sexualizar de forma proibida.
- Se houver duvida, responda com baixa ou media confianca e nao force violacao.

Retorne EXATAMENTE neste formato de 4 linhas:
VIOLATION: YES ou NO
CONFIDENCE: HIGH, MEDIUM ou LOW
CATEGORY: hate, harassment, sexual, threat, safe ou other
ACTION_REASON: uma frase curta em portugues explicando a decisao
"""


async def send_admin_msg(bot, channel_id, title, msg, is_error=False, icon=None, fallback=""):
    from utils.containers import container, section, send_components, e as emoji, parse_emojis

    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "X") if is_error else emoji("wCheck", "OK"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class ModerationCog(commands.Cog, name="Moderacao"):
    """Ferramentas de moderacao inteligente com IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam_cache = {}
        self.text_risk_patterns = {
            term: re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for term in TEXT_RISK_TERMS
        }

    def _find_text_risk_terms(self, content: str) -> list[str]:
        """Retorna termos sensiveis que exigem revisao contextual."""
        hits = [
            term
            for term, pattern in self.text_risk_patterns.items()
            if pattern.search(content)
        ]
        return sorted(set(hits))

    def _parse_text_moderation_result(self, response: str) -> dict | None:
        """Converte a resposta do classificador para um formato previsivel."""
        fields = {}
        for raw_line in response.splitlines():
            line = raw_line.strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip().upper()] = value.strip()

        violation = fields.get("VIOLATION", "").upper()
        confidence = fields.get("CONFIDENCE", "").upper()
        category = fields.get("CATEGORY", "").lower()
        action_reason = fields.get("ACTION_REASON", "").strip()

        if violation not in {"YES", "NO"}:
            return None
        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            return None
        if category not in {"hate", "harassment", "sexual", "threat", "safe", "other"}:
            return None

        return {
            "violation": violation == "YES",
            "confidence": confidence,
            "category": category,
            "action_reason": action_reason or "Analise contextual do AutoMod.",
        }

    async def _classify_text_violation(self, message: discord.Message, risk_terms: list[str]) -> dict | None:
        """Analisa contexto textual antes de punir automaticamente."""
        text = (message.clean_content or message.content or "").strip()
        if not text:
            return None

        prompt = (
            f"{AUTOMOD_TEXT_PROMPT}\n\n"
            f"Servidor: {message.guild.name}\n"
            f"Canal: #{getattr(message.channel, 'name', 'desconhecido')}\n"
            f"Autor: {message.author.display_name}\n"
            f"Termos sensiveis detectados: {', '.join(risk_terms)}\n"
            f"Mensagem:\n\"\"\"\n{text[:1500]}\n\"\"\""
        )

        response, error = await ollama.generate_simple(prompt)
        if error or not response:
            logger.warning(
                "AutoMod textual falhou na analise da mensagem %s: %s",
                message.id,
                error or "resposta vazia",
            )
            return None

        parsed = self._parse_text_moderation_result(response)
        if not parsed:
            logger.warning(
                "AutoMod textual recebeu resposta invalida para a mensagem %s: %r",
                message.id,
                response[:300],
            )
            return None

        return parsed

    async def _apply_punishment(self, member: discord.Member, guild: discord.Guild, reason: str, minutes: int):
        """Aplica warn e timeout ao usuario pelo AutoMod."""
        import datetime
        from utils.containers import container, section, e as emoji, parse_emojis

        try:
            duration = datetime.timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)

            await db.get_or_create_user(member.id, member.display_name)
            await db.add_warning(member.id, guild.id, self.bot.user.id, f"[AutoMod] {reason}")

            walert = emoji("wAlert", "!")
            text = (
                f"**{walert} Restricao Automatica**\n\n"
                f"**Motivo:** {parse_emojis(reason)}\n"
                f"**Tempo de mute:** `{minutes} minutos`."
            )

            try:
                from utils.containers import send_components

                await send_components(self.bot, member.id, [container([section(text)])])
            except Exception:
                pass

        except discord.Forbidden:
            logger.error("AutoMod falhou: sem permissao para penalizar %s", member.display_name)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if is_staff_member(message.author):
            return

        if message.attachments:
            from utils.image_scanner import scan_attachment_nsfw

            for attachment in message.attachments:
                if await scan_attachment_nsfw(attachment):
                    await message.delete()
                    await self._apply_punishment(
                        message.author,
                        message.guild,
                        "Imagem explicitamente proibida detectada.",
                        10,
                    )
                    return

        content = message.content or ""
        content_lower = content.lower()

        if "discord.gg/" in content_lower or "discord.com/invite/" in content_lower:
            await message.delete()
            await self._apply_punishment(message.author, message.guild, "Divulgacao de servidor proibida.", 5)
            return

        if len(message.mentions) > 4:
            await message.delete()
            await self._apply_punishment(message.author, message.guild, "Abuso de mencoes (Flood de ping).", 10)
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

        risk_terms = self._find_text_risk_terms(content)
        if not risk_terms:
            return

        logger.info(
            "AutoMod textual sinalizou a mensagem %s de %s para revisao contextual. Termos: %s",
            message.id,
            message.author.display_name,
            ", ".join(risk_terms),
        )

        verdict = await self._classify_text_violation(message, risk_terms)
        if not verdict:
            return

        logger.info(
            "AutoMod textual analisou a mensagem %s: violation=%s confidence=%s category=%s",
            message.id,
            verdict["violation"],
            verdict["confidence"],
            verdict["category"],
        )

        if not verdict["violation"] or verdict["confidence"] != "HIGH":
            return

        reason = f"{verdict['action_reason']} [categoria: {verdict['category']}]"
        logger.warning(
            "AutoMod textual puniu a mensagem %s de %s apos analise contextual. Motivo: %s",
            message.id,
            message.author.display_name,
            reason,
        )
        await message.delete()
        await self._apply_punishment(message.author, message.guild, reason, 5)

    @commands.command(name="analisar")
    async def cmd_analisar(self, ctx: commands.Context, *, texto: str):
        """Analisa o sentimento de um texto. Uso: !analisar <texto>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis

        async with ctx.channel.typing():
            prompt = (
                f"Analise o sentimento do seguinte texto:\n\n\"{texto}\"\n\n"
                "Responda EXATAMENTE neste formato:\n"
                "**Sentimento:** [Positivo/Negativo/Neutro/Misto]\n"
                "**Confianca:** [Alta/Media/Baixa]\n"
                "**Emocoes detectadas:** [lista de emocoes]\n"
                "**Analise:** [breve explicacao de 1-2 frases]"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Analise Falhou", erro, True)
            else:
                walert = emoji("wAlert", "INFO")
                text = f"**{walert} Analise de Sentimento**\n\n{parse_emojis(resposta[:1800])}\n\n-# Texto: {texto[:200]}"
                comps = [container([section(text)])]
                await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name="toxicidade")
    async def cmd_toxicidade(self, ctx: commands.Context, *, texto: str):
        """Verifica se um texto e toxico. Uso: !toxicidade <texto>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis

        async with ctx.channel.typing():
            prompt = (
                f"Analise a toxicidade do seguinte texto:\n\n\"{texto}\"\n\n"
                "Responda neste formato:\n"
                "**Nivel de toxicidade:** [0-10]\n"
                "**Classificacao:** [Seguro/Potencialmente ofensivo/Toxico/Altamente toxico]\n"
                "**Motivo:** [explicacao breve]\n"
                "**Contem:** [spam/discurso de odio/assedio/ameaca/conteudo sexual/nenhum]"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_admin_msg(self.bot, ctx.channel.id, "Monitoramento de Risco Falhou", erro, True)
            else:
                wshield = emoji("wShield", "Shield")
                text = f"**{wshield} Veredito de Toxicidade**\n\n{parse_emojis(resposta[:1800])}"
                comps = [container([section(text)])]
                await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name="regras")
    async def cmd_regras(self, ctx: commands.Context):
        """Mostra as regras do servidor."""
        from utils.containers import container, section, text_display, send_components, e as emoji

        wshield = emoji("wShield", "Shield")
        wlock = emoji("wLocked", "LOCK")
        regras = [
            "**1. Respeito** - Trate todos com respeito. Sem insultos, assedio ou discriminacao.",
            "**2. Sem Spam** - Nao faca spam de mensagens, links ou mencoes.",
            "**3. Canais Corretos** - Use cada canal para seu proposito.",
            "**4. Sem NSFW** - Conteudo adulto proibido em todos os canais.",
            "**5. Sem Pirataria** - Nao compartilhe conteudo pirata ou links ilegais.",
            "**6. Privacidade** - Nao compartilhe dados pessoais de outros membros.",
            "**7. Bot** - Use os comandos do bot de forma responsavel.",
            "**8. Portugues** - Comunique-se preferencialmente em portugues.",
        ]
        text = f"**{wshield} Regras do Servidor**\n\n" + "\n".join(regras)
        comps = [container([section(text), text_display(f"-# {wlock} Violacoes podem resultar em punicao severa e banimento.")])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name="reescrever")
    async def cmd_reescrever(self, ctx: commands.Context, *, texto: str):
        """Reescreve texto de forma mais profissional. Uso: !reescrever <texto>"""
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
                wfix = emoji("wFix", "EDIT")
                text = (
                    f"**{wfix} Texto Reescrito**\n\n"
                    f"{parse_emojis(resposta[:1500])}\n\n"
                    f"-# Original submetido: {texto[:200]}"
                )
                comps = [container([section(text)])]
                await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name="warn")
    @admin_only()
    async def cmd_warn(self, ctx: commands.Context, membro: discord.Member, *, motivo: str):
        """Da um aviso a um membro. Admin. Uso: !warn @user <motivo>"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis

        if not ctx.guild:
            return

        await db.get_or_create_user(membro.id, membro.display_name)
        warn_id = await db.add_warning(membro.id, ctx.guild.id, ctx.author.id, motivo)
        warnings = await db.get_warnings(membro.id, ctx.guild.id)
        walert = emoji("wAlert", "!")
        text = (
            f"**{walert} Aviso Administrativo Aplicado!**\n\n"
            f"- **Alvo Penalizado:** {membro.mention}\n"
            f"- **Motivo Documentado:** `{motivo}`\n"
            f"- **Juiz (Admin):** {ctx.author.mention}\n"
            f"- **Total de Strikes:** **{len(warnings)}** infracao(oes)\n\n"
            f"-# Ticket de Advertencia: #{warn_id}"
        )
        comps = [container([section(text)])]
        await send_components(self.bot, ctx.channel.id, comps)
        try:
            msg_dm = (
                f"**{walert} Voce tomou uma advertencia (Warn) em {ctx.guild.name}!**\n\n"
                f"**Motivo:** {parse_emojis(motivo)}\n"
                f"**Total de Strikes:** {len(warnings)}"
            )
            await send_components(self.bot, membro.id, [container([section(msg_dm)])])
        except Exception:
            pass

    @commands.command(name="avisos")
    @admin_only()
    async def cmd_avisos(self, ctx: commands.Context, membro: discord.Member):
        """Lista avisos de um membro. Admin. Uso: !avisos @user"""
        from utils.containers import container, section, send_components, e as emoji, parse_emojis

        if not ctx.guild:
            return

        warnings = await db.get_warnings(membro.id, ctx.guild.id)
        walert = emoji("wAlert", "!")
        if not warnings:
            comps = [container([section(f"**{walert} Historico Criminal - {membro.display_name}**\n\nA ficha deste usuario esta limpa.")])]
            await send_components(self.bot, ctx.channel.id, comps)
            return

        lines = [f"**{walert} Ficha Administrativa - {membro.display_name}** ({len(warnings)} infracao(oes))\n"]
        for warning in warnings[:10]:
            from datetime import datetime as dt

            try:
                ts = dt.fromisoformat(warning["timestamp"]).strftime("%d/%m/%Y %H:%M")
            except Exception:
                ts = "N/A"
            lines.append(f"- `#{warning['id']}` `{ts}` - {parse_emojis(warning['reason'][:150])}")

        comps = [container([section("\n".join(lines))])]
        await send_components(self.bot, ctx.channel.id, comps)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
