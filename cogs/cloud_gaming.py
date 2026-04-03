"""
Cog Cloud Gaming - comandos focados em atendimento de cloud gaming.
"""

import logging
import os

import discord
from discord.ext import commands

from utils.ollama_client import ollama
from utils.containers import container, section, send_components, e as emoji, parse_emojis

logger = logging.getLogger(__name__)


async def send_panel(bot, channel_id: int, title: str, content: str, icon: str = "wCloud", fallback: str = "cloud"):
    """Envia um painel compacto via containers."""
    wicon = emoji(icon, fallback)
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(content)[:3800]}"
    await send_components(bot, channel_id, [container([section(text)])])


def _load_knowledge() -> str:
    """Carrega a base oficial de conhecimento usada nas recomendacoes."""
    kb_path = os.path.join("data", "oris_knowledge.txt")
    if not os.path.exists(kb_path):
        return ""
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        logger.error(f"Erro ao ler base de cloud gaming: {exc}")
        return ""


class CloudGamingCog(commands.Cog, name="Cloud Gaming"):
    """Ferramentas de IA para cloud gaming, setup e suporte gamer."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.knowledge = _load_knowledge()

    def _prompt_base(self) -> str:
        return (
            "Voce e um especialista em cloud gaming da Oris Cloud. "
            "Responda em portugues do Brasil, de forma objetiva, util e comercial sem mentir. "
            "Use apenas as informacoes confirmadas da base abaixo para falar de planos, precos e limites. "
            "Se faltarem dados, diga que precisa de ticket humano.\n\n"
            f"{self.knowledge}\n"
        )

    @commands.command(name="planogamer")
    async def cmd_planogamer(self, ctx: commands.Context, *, necessidade: str):
        """Recomenda um plano para cloud gaming. Uso: !planogamer <jogo/uso>"""
        async with ctx.channel.typing():
            prompt = (
                f"{self._prompt_base()}\n"
                "Analise a necessidade abaixo e recomende o plano mais coerente da Oris Cloud. "
                "Considere jogo, resolucao, fps, uso casual ou competitivo e custo-beneficio.\n\n"
                f"Necessidade do cliente: {necessidade}\n\n"
                "Formato:\n"
                "**Plano recomendado:** ...\n"
                "**Motivo tecnico:** ...\n"
                "**Faixa de uso ideal:** ...\n"
                "**Quando abrir ticket:** ...\n"
                "Maximo 8 linhas."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_panel(self.bot, ctx.channel.id, "Falha na recomendacao", erro, "wAlert", "alerta")
            else:
                await send_panel(self.bot, ctx.channel.id, "Plano Gamer", resposta, "wRTX", "gamer")

    @commands.command(name="diaglag")
    async def cmd_diaglag(self, ctx: commands.Context, *, sintoma: str):
        """Diagnostica lag, stutter e input delay. Uso: !diaglag <problema>"""
        async with ctx.channel.typing():
            prompt = (
                "Voce e um analista de suporte para cloud gaming. "
                "Monte um diagnostico pratico para lag, stutter, packet loss, input delay ou queda de fps.\n\n"
                f"Sintoma relatado: {sintoma}\n\n"
                "Formato:\n"
                "**Causa provavel:** ...\n"
                "**Checklist rapido:**\n"
                "1. ...\n"
                "2. ...\n"
                "3. ...\n"
                "**Escalar para ticket quando:** ...\n"
                "Seja objetivo e tecnico."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_panel(self.bot, ctx.channel.id, "Falha no diagnostico", erro, "wAlert", "alerta")
            else:
                await send_panel(self.bot, ctx.channel.id, "Diagnostico de Lag", resposta, "wAlert", "latencia")

    @commands.command(name="setupcloud")
    async def cmd_setupcloud(self, ctx: commands.Context, *, objetivo: str):
        """Monta um checklist de setup para cloud gaming. Uso: !setupcloud <objetivo>"""
        async with ctx.channel.typing():
            prompt = (
                "Voce e um assistente tecnico de cloud gaming. "
                "Crie um checklist inicial para deixar uma VM pronta para jogar com boa estabilidade.\n\n"
                f"Objetivo do cliente: {objetivo}\n\n"
                "Formato:\n"
                "**Checklist de setup:**\n"
                "1. ...\n"
                "2. ...\n"
                "3. ...\n"
                "4. ...\n"
                "**Erro comum:** ...\n"
                "**Quando chamar suporte:** ...\n"
                "Foque em GPU, drivers, parsec ou streaming, rede e armazenamento."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_panel(self.bot, ctx.channel.id, "Falha no setup", erro, "wAlert", "alerta")
            else:
                await send_panel(self.bot, ctx.channel.id, "Setup Cloud Gaming", resposta, "wFix2", "setup")

    @commands.command(name="jogocloud")
    async def cmd_jogocloud(self, ctx: commands.Context, *, jogo: str):
        """Analisa se um jogo faz sentido na cloud. Uso: !jogocloud <jogo>"""
        async with ctx.channel.typing():
            prompt = (
                "Analise se o jogo abaixo faz sentido em cloud gaming. "
                "Considere sensibilidade a latencia, necessidade de GPU, estabilidade de rede e perfil do jogador.\n\n"
                f"Jogo: {jogo}\n\n"
                "Formato:\n"
                "**Vale a pena na cloud?** Sim/Depende/Nao\n"
                "**Ponto critico:** ...\n"
                "**Perfil ideal:** ...\n"
                "**Recomendacao pratica:** ...\n"
                "Nao invente benchmark."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_panel(self.bot, ctx.channel.id, "Falha na analise", erro, "wAlert", "alerta")
            else:
                await send_panel(self.bot, ctx.channel.id, "Analise de Jogo na Cloud", resposta, "wCloud", "cloud")


async def setup(bot: commands.Bot):
    await bot.add_cog(CloudGamingCog(bot))
