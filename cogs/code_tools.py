"""
Cog Code Tools — Geração, análise, debug e otimização de código via IA.
"""

import discord
from discord.ext import commands
import logging

from utils.ollama_client import ollama
from utils.helpers import split_message
from utils.containers import container, section, send_components, e as emoji, parse_emojis

logger = logging.getLogger(__name__)

async def send_error(bot, channel_id, title, erro_msg):
    werror = emoji("wCancel", "🛑")
    text = f"**{werror} {parse_emojis(title)}**\n\n{parse_emojis(erro_msg)}"
    await send_components(bot, channel_id, [container([section(text)])])

async def send_code_chunks(bot, channel_id, title, full_text):
    wicon = emoji("wTerminal", "💻")
    parts = split_message(parse_emojis(full_text))
    for i, part in enumerate(parts):
        header = f"**{wicon} {parse_emojis(title)}**\n\n" if i == 0 else ""
        await send_components(bot, channel_id, [container([section(f"{header}{part}")])])


class CodeToolsCog(commands.Cog, name="💻 Code Tools"):
    """Ferramentas de programação com IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _code_task(self, ctx, prompt: str, title: str):
        """Executa uma tarefa de código genérica."""
        async with ctx.channel.typing():
            resposta, erro = await ollama.generate_simple(prompt)
            if erro:
                await send_error(self.bot, ctx.channel.id, f"Falha: {title}", erro)
            else:
                await send_code_chunks(self.bot, ctx.channel.id, title, resposta)

    @commands.command(name='code')
    async def cmd_code(self, ctx: commands.Context, linguagem: str, *, descricao: str):
        """💻 Gera código. Uso: !code <linguagem> <descrição>"""
        prompt = (
            f"Gere código em **{linguagem}** para: {descricao}\n\n"
            "Regras:\n"
            "- Código limpo e bem comentado\n"
            "- Use boas práticas da linguagem\n"
            "- Inclua exemplo de uso\n"
            "- Formate dentro de blocos de código markdown"
        )
        await self._code_task(ctx, prompt, "Geração de Código")

    @commands.command(name='explicar')
    async def cmd_explicar(self, ctx: commands.Context, *, codigo: str):
        """🔍 Explica o que um código faz. Uso: !explicar <código>"""
        prompt = (
            f"Explique detalhadamente o que este código faz:\n\n{codigo}\n\n"
            "Inclua:\n"
            "1. O que cada parte faz\n"
            "2. O fluxo de execução\n"
            "3. Possíveis problemas\n"
            "4. Complexidade computacional (se relevante)"
        )
        await self._code_task(ctx, prompt, "Explicação de Código")

    @commands.command(name='bug')
    async def cmd_bug(self, ctx: commands.Context, *, codigo: str):
        """🐛 Analisa bugs no código. Uso: !bug <código>"""
        prompt = (
            f"Analise este código em busca de bugs, erros e problemas:\n\n{codigo}\n\n"
            "Para cada bug encontrado:\n"
            "1. 🐛 Descreva o problema\n"
            "2. 📍 Indique onde está\n"
            "3. ✅ Mostre a correção\n"
            "Se o código estiver correto, diga isso claramente."
        )
        await self._code_task(ctx, prompt, "Análise de Bugs")

    @commands.command(name='otimizar')
    async def cmd_otimizar(self, ctx: commands.Context, *, codigo: str):
        """⚡ Sugere otimizações para o código. Uso: !otimizar <código>"""
        prompt = (
            f"Analise e otimize este código:\n\n{codigo}\n\n"
            "Mostre:\n"
            "1. ⚡ Versão otimizada do código\n"
            "2. 📊 O que mudou e por quê\n"
            "3. 🚀 Ganho esperado de performance\n"
            "Se já estiver otimizado, diga isso."
        )
        await self._code_task(ctx, prompt, "Otimização de Código")

    @commands.command(name='regex')
    async def cmd_regex(self, ctx: commands.Context, *, descricao: str):
        """🔤 Gera expressão regex. Uso: !regex <descrição>"""
        prompt = (
            f"Crie uma expressão regular (regex) para: {descricao}\n\n"
            "Inclua:\n"
            "1. A regex\n"
            "2. Explicação de cada parte\n"
            "3. Exemplos de matches e não-matches\n"
            "4. Código de exemplo em Python"
        )
        await self._code_task(ctx, prompt, "Expressão Regular (Regex)")

    @commands.command(name='sql')
    async def cmd_sql(self, ctx: commands.Context, *, descricao: str):
        """🗃️ Gera query SQL. Uso: !sql <descrição>"""
        prompt = (
            f"Gere uma query SQL para: {descricao}\n\n"
            "Inclua:\n"
            "1. A query SQL formatada\n"
            "2. Explicação do que faz\n"
            "3. Considerações de performance\n"
            "Se precisar de tabelas, sugira a estrutura."
        )
        await self._code_task(ctx, prompt, "Estrutura SQL")

    @commands.command(name='json')
    async def cmd_json(self, ctx: commands.Context, *, descricao: str):
        """📋 Gera estrutura JSON. Uso: !json <descrição>"""
        prompt = (
            f"Gere uma estrutura JSON para: {descricao}\n\n"
            "Inclua:\n"
            "1. O JSON formatado\n"
            "2. Descrição de cada campo\n"
            "3. Tipos de dados usados"
        )
        await self._code_task(ctx, prompt, "Estrutura JSON")

    @commands.command(name='docstring')
    async def cmd_docstring(self, ctx: commands.Context, *, codigo: str):
        """📝 Gera documentação para código. Uso: !docstring <código>"""
        prompt = (
            f"Gere documentação completa (docstrings) para este código:\n\n{codigo}\n\n"
            "Inclua:\n"
            "1. Docstring para cada função/classe\n"
            "2. Parâmetros com tipos e descrição\n"
            "3. Retorno com tipo e descrição\n"
            "4. Exemplos de uso\n"
            "Use o formato Google-style docstring."
        )
        await self._code_task(ctx, prompt, "Documentação e Docstrings")

    @commands.command(name='arquitetura')
    async def cmd_arquitetura(self, ctx: commands.Context, *, descricao: str):
        """🏗️ Sugere arquitetura de software. Uso: !arquitetura <descrição do projeto>"""
        prompt = (
            f"Sugira uma arquitetura de software para: {descricao}\n\n"
            "Inclua:\n"
            "1. 🏗️ Arquitetura geral (camadas, componentes)\n"
            "2. 📁 Estrutura de pastas sugerida\n"
            "3. 🔧 Tecnologias recomendadas\n"
            "4. 📊 Diagrama textual da arquitetura\n"
            "5. ⚠️ Pontos de atenção"
        )
        await self._code_task(ctx, prompt, "Arquitetura de Software")


async def setup(bot: commands.Bot):
    await bot.add_cog(CodeToolsCog(bot))
