"""
Sistema de Permissões — Decorators para comandos admin-only.
"""

import discord
from discord.ext import commands
import functools
import logging

logger = logging.getLogger(__name__)


def admin_only():
    """
    Decorator que restringe o comando a administradores.
    Verifica a permissão 'administrator' do Discord.
    Em DMs, bloqueia o comando (não tem como verificar permissões).
    """
    async def predicate(ctx: commands.Context) -> bool:
        # Em DMs não tem como verificar permissão de servidor
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.send(
                embed=discord.Embed(
                    title="🔒 Comando de Admin",
                    description="Este comando só pode ser usado em servidores, por administradores.",
                    color=0xED4245
                )
            )
            return False

        # Verifica se é admin
        if ctx.author.guild_permissions.administrator:
            return True

        # Não é admin
        await ctx.send(
            embed=discord.Embed(
                title="🔒 Sem Permissão",
                description=(
                    f"**{ctx.author.display_name}**, você precisa da permissão "
                    f"de **Administrador** para usar `!{ctx.command.name}`.\n\n"
                    f"Peça a um admin do servidor."
                ),
                color=0xED4245
            )
        )
        return False

    return commands.check(predicate)


def owner_only():
    """Decorator para comandos exclusivos do dono do servidor."""
    async def predicate(ctx: commands.Context) -> bool:
        if isinstance(ctx.channel, discord.DMChannel):
            return False

        if ctx.author.id == ctx.guild.owner_id:
            return True

        await ctx.send(
            embed=discord.Embed(
                title="👑 Apenas o Dono",
                description="Este comando é exclusivo para o dono do servidor.",
                color=0xED4245
            )
        )
        return False

    return commands.check(predicate)
