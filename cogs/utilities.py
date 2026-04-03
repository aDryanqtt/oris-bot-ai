"""
Cog Utilitários — Tradução, resumo, correção, cálculos, piadas e mais.
"""

import discord
from discord.ext import commands
import logging

from utils.ollama_client import ollama
from utils.helpers import split_message
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis

logger = logging.getLogger(__name__)

async def send_error(bot, channel_id, title, erro_msg):
    werror = emoji("wCancel", "🛑")
    text = f"**{werror} {parse_emojis(title)}**\n\n{parse_emojis(erro_msg)}"
    await send_components(bot, channel_id, [container([section(text)])])

async def send_info(bot, channel_id, title, content, icon="wInfo", fallback="💠", footer=None):
    wicon = emoji(icon, fallback)
    comps = [section(f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(content)[:4096]}")]
    if footer:
        comps.append(text_display(f"-# {parse_emojis(footer)}"))
    await send_components(bot, channel_id, [container(comps)])

async def send_split(bot, channel_id, title, full_text, icon="wInfo", fallback="💠"):
    wicon = emoji(icon, fallback)
    parts = split_message(parse_emojis(full_text))
    for i, part in enumerate(parts):
        header = f"**{wicon} {parse_emojis(title)}**\n\n" if i == 0 else ""
        await send_components(bot, channel_id, [container([section(f"{header}{part}")])])


class UtilitiesCog(commands.Cog, name="🛠️ Utilitários"):
    """Ferramentas utilitárias diversas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='traduzir')
    async def cmd_traduzir(self, ctx: commands.Context, idioma: str, *, texto: str):
        """🌐 Traduz texto. Uso: !traduzir <idioma> <texto>"""
        async with ctx.channel.typing():
            prompt = (
                f"Traduza o seguinte texto para {idioma}. "
                f"Retorne APENAS a tradução, sem explicações:\n\n{texto}"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro de Tradução", erro)
            else:
                await send_info(self.bot, ctx.channel.id, f"Tradução → {idioma.title()}", resposta, "wGlobe", "🌐", f"Original: {texto[:200]}")

    @commands.command(name='resumirtexto')
    async def cmd_resumirtexto(self, ctx: commands.Context, *, texto: str):
        """📋 Resume um texto longo. Uso: !resumirtexto <texto>"""
        async with ctx.channel.typing():
            prompt = (
                f"Resuma o seguinte texto de forma concisa, mantendo os pontos principais:\n\n{texto}\n\n"
                "Formato:\n"
                "- **Resumo:** (2-3 frases)\n"
                "- **Pontos principais:** (lista)"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro no Resumo", erro)
            else:
                await send_info(self.bot, ctx.channel.id, "Resumo de Texto", resposta, "wList", "📋")

    @commands.command(name='corrigir')
    async def cmd_corrigir(self, ctx: commands.Context, *, texto: str):
        """✏️ Corrige gramática e ortografia. Uso: !corrigir <texto>"""
        async with ctx.channel.typing():
            prompt = (
                f"Corrija a gramática e ortografia do seguinte texto em português:\n\n{texto}\n\n"
                "Formato de resposta:\n"
                "**Texto corrigido:**\n(texto)\n\n"
                "**Correções feitas:**\n(lista das correções)"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro na Correção", erro)
            else:
                await send_split(self.bot, ctx.channel.id, "Correção Ortográfica", resposta, "wFix", "✏️")

    @commands.command(name='explicarcomo')
    async def cmd_explicarcomo(self, ctx: commands.Context, *, assunto: str):
        """📚 Explica como fazer algo passo-a-passo. Uso: !explicarcomo <assunto>"""
        async with ctx.channel.typing():
            prompt = (
                f"Explique passo-a-passo como: {assunto}\n\n"
                "Use formato:\n"
                "**Passo 1:** ...\n"
                "**Passo 2:** ...\n"
                "etc.\n\n"
                "Seja prático e direto. Inclua dicas úteis."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro de Explicação", erro)
            else:
                await send_split(self.bot, ctx.channel.id, "Como fazer", resposta, "wBook", "📚")

    @commands.command(name='calcular')
    async def cmd_calcular(self, ctx: commands.Context, *, expressao: str):
        """🔢 Resolve cálculos. Uso: !calcular <expressão>"""
        async with ctx.channel.typing():
            safe_result = None
            try:
                allowed = set('0123456789+-*/.() ')
                if all(c in allowed for c in expressao):
                    safe_result = eval(expressao)
            except Exception:
                pass

            if safe_result is not None:
                await send_info(self.bot, ctx.channel.id, "Cálculo Rápido", f"**{expressao}** = **{safe_result}**", "wFix2", "🔢")
            else:
                prompt = (
                    f"Resolva o seguinte cálculo/problema matemático: {expressao}\n\n"
                    "Mostre:\n"
                    "1. A resolução passo-a-passo\n"
                    "2. O resultado final destacado"
                )
                resposta, erro = await ollama.generate_simple(prompt)
                if erro:
                    await send_error(self.bot, ctx.channel.id, "Erro de Cálculo", erro)
                else:
                    await send_split(self.bot, ctx.channel.id, "Resolução Matemática", resposta, "wFix2", "🔢")

    @commands.command(name='piada')
    async def cmd_piada(self, ctx: commands.Context):
        """😂 Conta uma piada."""
        async with ctx.channel.typing():
            prompt = "Conte uma piada engraçada e criativa em português. Pode ser sobre tecnologia, programação, ou do dia-a-dia. Seja original!"
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Sem Graça", "Não consegui pensar em nenhuma piada... 😅")
            else:
                await send_info(self.bot, ctx.channel.id, "Humor Artificial", resposta, "wLaugh", "😂")

    @commands.command(name='fato')
    async def cmd_fato(self, ctx: commands.Context):
        """🧠 Conta um fato interessante."""
        async with ctx.channel.typing():
            prompt = (
                "Conte um fato surpreendente e interessante. Pode ser sobre ciência, história, natureza ou tecnologia. "
                "Seja preciso — NÃO invente fatos. Se não tiver certeza, escolha outro fato que você sabe ser verdadeiro."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro Factual", erro)
            else:
                await send_info(self.bot, ctx.channel.id, "Fato Interessante", resposta, "wBrain", "🧠")

    @commands.command(name='conselho')
    async def cmd_conselho(self, ctx: commands.Context):
        """💡 Dá um conselho ou frase motivacional."""
        async with ctx.channel.typing():
            prompt = "Dê um conselho sábio ou frase motivacional. Seja inspirador e original."
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro Conselheiro", erro)
            else:
                await send_info(self.bot, ctx.channel.id, "Conselho Sábio", resposta, "wLight", "💡")

    @commands.command(name='definir')
    async def cmd_definir(self, ctx: commands.Context, *, termo: str):
        """📖 Define um termo ou conceito. Uso: !definir <termo>"""
        async with ctx.channel.typing():
            prompt = (
                f"Defina o termo/conceito: '{termo}'\n\n"
                "Inclua:\n"
                "1. **Definição** clara e concisa\n"
                "2. **Exemplo** de uso\n"
                "3. **Contexto** (em que área é usado)\n"
                "Se não souber com certeza, diga claramente."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Definição não encontrada", erro)
            else:
                await send_info(self.bot, ctx.channel.id, f"Significado: {termo.title()}", resposta, "wBook", "📖")

    @commands.command(name='comparar')
    async def cmd_comparar(self, ctx: commands.Context, *, itens: str):
        """⚖️ Compara dois ou mais itens. Uso: !comparar item1 vs item2"""
        async with ctx.channel.typing():
            prompt = (
                f"Compare de forma detalhada e imparcial: {itens}\n\n"
                "Formato:\n"
                "| Critério | Item A | Item B |\n"
                "|---|---|---|\n"
                "... (tabela comparativa)\n\n"
                "**Conclusão:** qual é melhor para cada caso de uso."
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Erro de Comparação", erro)
            else:
                await send_split(self.bot, ctx.channel.id, "Comparativo Analítico", resposta, "wScale", "⚖️")

    @commands.command(name='listaideias')
    async def cmd_listaideias(self, ctx: commands.Context, *, tema: str):
        """💡 Gera lista de ideias sobre um tema. Uso: !listaideias <tema>"""
        async with ctx.channel.typing():
            prompt = (
                f"Gere 10 ideias criativas e práticas sobre: {tema}\n\n"
                "Para cada ideia:\n"
                "- Número e título\n"
                "- Breve descrição (1-2 frases)\n"
                "Seja criativo e inovador!"
            )
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, "Bloqueio Criativo", erro)
            else:
                await send_split(self.bot, ctx.channel.id, f"10 Ideias: {tema.title()[:30]}", resposta, "wLight", "💡")


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilitiesCog(bot))

