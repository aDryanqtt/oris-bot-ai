"""
Cog Perfil — Sistema de XP, níveis e perfil do usuário.
"""

import discord
from discord.ext import commands
import logging
from datetime import datetime as dt

from utils.database import db
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from config import COLOR_PROFILE, COIN_SYMBOL, COIN_EMOJI, now_br, format_datetime_br

logger = logging.getLogger(__name__)

async def send_error(bot, channel_id, title, erro_msg):
    werror = emoji("wCancel", "🛑")
    text = f"**{werror} {parse_emojis(title)}**\n\n{parse_emojis(erro_msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class ProfileCog(commands.Cog, name="👤 Perfil"):
    """Sistema de perfil, XP e níveis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='perfil')
    async def cmd_perfil(self, ctx: commands.Context, membro: discord.Member = None):
        """👤 Mostra seu perfil ou de outro membro. Uso: !perfil [@user]"""
        target = membro or ctx.author

        user_data = await db.get_or_create_user(target.id, target.display_name)
        eco_data = await db.get_economy_profile(target.id)

        level = user_data['level']
        xp = user_data['xp']
        next_level_xp = level * 100
        xp_progress = min(xp / next_level_xp * 100, 100) if next_level_xp > 0 else 0
        filled = int(xp_progress / 10)
        bar = '█' * filled + '░' * (10 - filled)

        wuser = emoji("wUser", "👤")
        wcash = emoji("wCash", "💰")
        wfire = emoji("wFire", "🔥")

        try:
            first = dt.fromisoformat(user_data['first_seen'])
            membro_desde = format_datetime_br(first)
        except Exception:
            membro_desde = "N/A"

        text = (
            f"**{wuser} Perfil — {target.display_name}**\n\n"
            f"**Nível & XP**\n"
            f"{bar} {xp_progress:.0f}%\n"
            f"Nível `{level}` • {xp}/{next_level_xp} XP\n\n"
            f"**Atividade Geral**\n"
            f"• Mensagens enviadas: `{user_data['total_messages']:,}`\n"
            f"• Comandos Oris: `{user_data['total_commands']:,}`\n\n"
            f"**{wcash} Economia**\n"
            f"• Saldo disponível: `{eco_data['balance']:,} {COIN_SYMBOL}`\n"
            f"• Streak ativo: {wfire} `{eco_data['daily_streak']} dias`\n\n"
            f"• Membro desde: {membro_desde}\n"
            f"• Persona avaliada: `{user_data['persona']}`"
        )

        avatar = str(target.display_avatar.url) if target.display_avatar else None
        comps = [container([section(text, avatar)])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='top')
    async def cmd_top(self, ctx: commands.Context):
        """🏆 Ranking de XP do servidor."""
        if not ctx.guild:
            await send_error(self.bot, ctx.channel.id, "Ranking Inválido", "Use este comando dentro de um servidor.")
            return

        member_ids = [m.id for m in ctx.guild.members if not m.bot]
        top = await db.get_top_users(member_ids, limit=10)

        wtrophy = emoji("wTrophy", "🏆")
        
        if not top:
            await send_components(self.bot, ctx.channel.id, [
                container([section(f"**{wtrophy} Ranking de XP**\n\nNinguém tem XP ainda! Comecem a interagir para ganhar.")])
            ])
            return

        medalhas = ['🥇', '🥈', '🥉']
        lines = [f"**{wtrophy} Ranking de XP — {ctx.guild.name}**\n"]
        
        for i, entry in enumerate(top):
            medalha = medalhas[i] if i < 3 else f'`#{i+1}`'
            lines.append(
                f"{medalha} **{entry['username']}** — "
                f"Nível `{entry['level']}` • `{entry['xp']} XP` • "
                f"`{entry['total_messages']:,}` msgs"
            )

        comps = [container([section("\n".join(lines)), text_display("-# Ganhe XP conversando na nuvem do servidor!")])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='serverinfo')
    async def cmd_serverinfo(self, ctx: commands.Context):
        """🏠 Informações detalhadas do servidor."""
        if not ctx.guild:
            await send_error(self.bot, ctx.channel.id, "Informação do Servidor", "Use este comando dentro do servidor.")
            return

        guild = ctx.guild
        total = guild.member_count or 0
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots
        
        try:
            online = sum(1 for m in guild.members if m.status and m.status != discord.Status.offline)
        except Exception:
            online = 0

        roles = len(guild.roles) - 1
        emojis_count = len(guild.emojis)
        stats = await db.get_bot_stats()

        whome = emoji("wHome", "🏠")
        wshield = emoji("wShield", "🛡️")
        wcloud = emoji("wCloud", "☁️")

        owner_mention = guild.owner.mention if guild.owner else "N/A"
        created = guild.created_at.strftime("%d/%m/%Y")

        text = (
            f"**{whome} {guild.name}**\n"
            f"`{guild.id}`\n\n"
            f"**👥 Corpo de Membros**\n"
            f"• Total de membros: `{total:,}`\n"
            f"• Humanos reais: `{humans:,}`\n"
            f"• Robôs na infra: `{bots:,}`\n"
            f"• Usuários Online: `{online:,}`\n\n"
            f"**💬 Relatório de Canais**\n"
            f"• Texto: `{len(guild.text_channels)}` • Voz: `{len(guild.voice_channels)}` • Categorias: `{len(guild.categories)}`\n\n"
            f"**{wshield} Nível do Servidor**\n"
            f"• Cargos listados: `{roles}`\n"
            f"• Emojis em cache: `{emojis_count}`\n"
            f"• Nível de Impulso: `{guild.premium_tier}`\n"
            f"• Administrador Mor: {owner_mention}\n"
            f"• Data de Fundação: `{created}`\n\n"
            f"**{wcloud} Estatísticas Sistêmicas Oris Cloud**\n"
            f"• Usuários registrados em banco: `{stats['total_users']}`\n"
            f"• Total de requisições de comando: `{stats['total_commands']:,}`\n"
            f"• Volumetria de tráfego de mensagens: `{stats['total_messages']:,}`"
        )

        icon_url = str(guild.icon.url) if guild.icon else None
        comps = [container([section(text, icon_url)])]
        await send_components(self.bot, ctx.channel.id, comps)

async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
