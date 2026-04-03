"""
Builder de Embeds padronizados — Configuração Tier 17 (Premium UI).
Usa horário de Brasília em todos os timestamps, barras laterais coloridas super saturadas.
"""

import discord
from config import (
    COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, COLOR_WARNING,
    COLOR_AI, COLOR_AWS, COLOR_CODE, now_br
)

import os
import json

def get_emoji(nome_desejado: str, fallback: str) -> str:
    """Busca o emoji customizado do pacote premium ou cai matando no fallback unicode."""
    try:
        caminho = os.path.join("data", "emojis.json")
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(nome_desejado, fallback)
    except:
        pass
    return fallback

import re

def parse_emojis(texto: str) -> str:
    """Injeta as figurinhas formatadas `<:nome:id>`, varrendo texto da IA de forma segura contra dupes."""
    if not texto: return texto
    try:
        caminho = os.path.join("data", "emojis.json")
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
            def replacer(match):
                name = match.group(1)
                return data.get(name, match.group(0))
            texto = re.sub(r'<:([a-zA-Z0-9_]+):\d+>', replacer, texto)
            return re.sub(r'(?<!<):([a-zA-Z0-9_]+):', replacer, texto)
    except:
        pass
    return texto

class EmbedBuilder:
    """Cria embeds Discord bonitos e padronizados com UX Imersiva."""

    @staticmethod
    def ai_response(content: str, author: discord.User = None, model: str = None) -> discord.Embed:
        """Embed com design neon/preto puro para respostas da IA."""
        content_with_emojis = parse_emojis(content)
        embed = discord.Embed(
            description=content_with_emojis[:4096],
            color=COLOR_AI,
            timestamp=now_br()
        )
        if model:
            wpy = get_emoji("wPy", "✨")
            embed.set_footer(text=f"{wpy} {model} | Oris Cloud", icon_url=None)
        if author:
            wuser = get_emoji("wUser", "🤖")
            embed.set_author(name=f"{wuser} Resposta para {author.display_name}", icon_url=author.display_avatar.url if author.display_avatar else None)
        return embed

    @staticmethod
    def success(title: str, description: str = None) -> discord.Embed:
        icone = get_emoji("wFix2", "✨")
        embed = discord.Embed(
            title=parse_emojis(f"{icone} {title}"),
            description=parse_emojis(description) if description else None,
            color=COLOR_SUCCESS,
            timestamp=now_br()
        )
        return embed

    @staticmethod
    def error(title: str, description: str = None) -> discord.Embed:
        icone = get_emoji("wCancel", "🛑")
        embed = discord.Embed(
            title=parse_emojis(f"{icone} {title}"),
            description=parse_emojis(description) if description else None,
            color=COLOR_ERROR,
            timestamp=now_br()
        )
        return embed

    @staticmethod
    def info(title: str, description: str = None) -> discord.Embed:
        icone = get_emoji("wInfo", "💠")
        embed = discord.Embed(
            title=parse_emojis(f"{icone} {title}"),
            description=parse_emojis(description) if description else None,
            color=COLOR_INFO,
            timestamp=now_br()
        )
        return embed

    @staticmethod
    def warning(title: str, description: str = None) -> discord.Embed:
        icone = get_emoji("wAlert", "⚠️")
        embed = discord.Embed(
            title=parse_emojis(f"{icone} {title}"),
            description=parse_emojis(description) if description else None,
            color=COLOR_WARNING,
            timestamp=now_br()
        )
        return embed

    @staticmethod
    def server_status(fields: dict) -> discord.Embed:
        """Embed de alta tecnologia para status do servidor AWS."""
        embed = discord.Embed(
            title="☁️ AWS Cloud Core Status",
            color=COLOR_AWS,
            timestamp=now_br()
        )
        for name, value in fields.items():
            embed.add_field(name=name, value=str(value), inline=True)
        return embed

    @staticmethod
    def code_block(title: str, code: str, language: str = "python") -> discord.Embed:
        """Embed clean e formatado para blocos de código."""
        embed = discord.Embed(
            title=f"💻 {title}",
            description=f"```{language}\n{code[:3900]}\n```",
            color=COLOR_CODE,
            timestamp=now_br()
        )
        return embed

    @staticmethod
    def dashboard(title: str, sections: dict) -> discord.Embed:
        """Embed dashboard Tier 17."""
        embed = discord.Embed(
            title=f"📊 {title}",
            color=COLOR_INFO,
            timestamp=now_br()
        )
        for section_name, section_value in sections.items():
            embed.add_field(
                name=f"🔹 {section_name}",
                value=str(section_value),
                inline=len(str(section_value)) < 50
            )
        embed.set_footer(text="Painel Interativo Oris")
        return embed

    @staticmethod
    def channel_analysis(channel_name: str, summary: str, stats: dict) -> discord.Embed:
        """Embed premium para análise de canal."""
        embed = discord.Embed(
            title=parse_emojis(f"🔍 Intelligence Report: #{channel_name}"),
            description=parse_emojis(summary)[:4096] if summary else None,
            color=COLOR_INFO,
            timestamp=now_br()
        )
        for name, value in stats.items():
            embed.add_field(name=name, value=str(value), inline=True)
        return embed

    @staticmethod
    def url_analysis(url: str, summary: str) -> discord.Embed:
        """Embed premium para análise de URL."""
        embed = discord.Embed(
            title="🔗 URL Scan Results",
            description=parse_emojis(summary)[:4096] if summary else None,
            color=COLOR_INFO,
            timestamp=now_br()
        )
        embed.add_field(name="Alvo", value=url[:1024], inline=False)
        return embed
