"""
Cog Economia — Sistema robusto de moedas virtuais (Oris Coin).
Todas as operações usam transações atômicas via database.py.
"""

import discord
from discord.ext import commands
import random
import logging

from utils.database import db
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from config import (
    COLOR_ECONOMY, COIN_NAME, COIN_EMOJI, COIN_SYMBOL,
    DAILY_BASE, DAILY_STREAK_BONUS, now_br
)

logger = logging.getLogger(__name__)

async def send_error(bot, channel_id, title, erro_msg):
    werror = emoji("wCancel", "🛑")
    text = f"**{werror} {parse_emojis(title)}**\n\n{parse_emojis(erro_msg)}"
    await send_components(bot, channel_id, [container([section(text)])])

class EconomyCog(commands.Cog, name="💰 Economia"):
    """Sistema de economia virtual com Oris Coins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='daily')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def cmd_daily(self, ctx: commands.Context):
        """🪙 Resgate sua recompensa diária de Oris Coins."""
        await db.get_or_create_user(ctx.author.id, ctx.author.display_name)
        sucesso, valor, streak, erro = await db.claim_daily(ctx.author.id)
        wcash = emoji("wCash", "🪙")
        wfire = emoji("wFire", "🔥")
        if not sucesso:
            await send_error(self.bot, ctx.channel.id, "Daily indisponível", erro)
            return

        saldo = await db.get_balance(ctx.author.id)
        bonus = valor - DAILY_BASE
        bonus_txt = f"\n• Bônus streak: `+{bonus} {COIN_SYMBOL}`" if bonus > 0 else ""
        streak_txt = f"\n\n{wfire} **Streak de {streak} dias!**" if streak >= 7 else ""
        avatar = str(ctx.author.display_avatar.url) if ctx.author.display_avatar else None
        text = (
            f"**{wcash} Recompensa Diária!**\n\n"
            f"• Recebidos: `+{valor} {COIN_SYMBOL}`{bonus_txt}\n"
            f"• Saldo atual: `{saldo:,} {COIN_SYMBOL}`\n"
            f"• Streak: {wfire} `{streak} dia{'s' if streak != 1 else ''}`"
            f"{streak_txt}\n\n-# Volte amanhã para manter seu streak!"
        )
        comps = [container([section(text, avatar)])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='saldo')
    async def cmd_saldo(self, ctx: commands.Context, membro: discord.Member = None):
        """💰 Veja seu saldo ou de outro membro. Uso: !saldo [@user]"""
        target = membro or ctx.author
        await db.get_or_create_user(target.id, target.display_name)
        perfil = await db.get_economy_profile(target.id)
        saldo = perfil['balance']
        total_earned = perfil['total_earned']
        total_spent = perfil['total_spent']
        streak = perfil['daily_streak']
        wcash = emoji("wCash", "💰")
        wfire = emoji("wFire", "🔥")
        avatar = str(target.display_avatar.url) if target.display_avatar else None
        text = (
            f"**{wcash} Carteira — {target.display_name}**\n\n"
            f"• Saldo: **{saldo:,} {COIN_SYMBOL}**\n"
            f"• Total ganho: `{total_earned:,} {COIN_SYMBOL}`\n"
            f"• Total gasto: `{total_spent:,} {COIN_SYMBOL}`\n"
            f"• Streak: {wfire} `{streak} dia{'s' if streak != 1 else ''}`"
        )
        comps = [container([section(text, avatar)])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='ranking')
    async def cmd_ranking(self, ctx: commands.Context):
        """🏆 Ranking dos mais ricos do servidor."""
        if not ctx.guild:
            await send_error(self.bot, ctx.channel.id, "Ranking", "Ação inválida: Use em um servidor.")
            return

        member_ids = [m.id for m in ctx.guild.members if not m.bot]
        top = await db.get_top_economy(member_ids, limit=10)
        wcash = emoji("wCash", "🏆")
        wfire = emoji("wFire", "🔥")
        if not top:
            comps = [container([section(f"**{wcash} Ranking — {COIN_NAME}**\n\nNinguém tem moedas ainda! Use `!daily` para começar.")])]
            await send_components(self.bot, ctx.channel.id, comps)
            return

        medalhas = ['🥇', '🥈', '🥉']
        lines = [f"**{wcash} Ranking — {COIN_NAME}**\n"]
        for i, entry in enumerate(top):
            medalha = medalhas[i] if i < 3 else f'`#{i+1}`'
            streak_str = f" {wfire}{entry['daily_streak']}" if entry['daily_streak'] >= 3 else ""
            lines.append(f"{medalha} **{entry['username']}** — `{entry['balance']:,} {COIN_SYMBOL}`{streak_str}")
        lines.append(f"\n-# Use `!daily` para ganhar {COIN_SYMBOL}")
        comps = [container([section("\n".join(lines))])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='transferir')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def cmd_transferir(self, ctx: commands.Context, membro: discord.Member, valor: int):
        """💸 Transfere moedas para outro membro. Uso: !transferir @user <valor>"""
        if membro.bot:
            await send_error(self.bot, ctx.channel.id, "Transferência Inválida", "Não pode transferir para bots!")
            return
        if valor <= 0:
            await send_error(self.bot, ctx.channel.id, "Valor Inválido", "O valor precisa ser MAIOR que 0!")
            return

        await db.get_or_create_user(ctx.author.id, ctx.author.display_name)
        await db.get_or_create_user(membro.id, membro.display_name)
        sucesso, mensagem = await db.transfer_coins(ctx.author.id, membro.id, valor)
        wcash = emoji("wCash", "💸")
        if sucesso:
            saldo_sender = await db.get_balance(ctx.author.id)
            saldo_receiver = await db.get_balance(membro.id)
            text = (
                f"**{wcash} Transferência Realizada!**\n\n"
                f"{ctx.author.display_name} → {membro.display_name}\n"
                f"• Valor: `{valor:,} {COIN_SYMBOL}`\n"
                f"• Seu saldo: `{saldo_sender:,} {COIN_SYMBOL}`\n"
                f"• Saldo de {membro.display_name}: `{saldo_receiver:,} {COIN_SYMBOL}`"
            )
            comps = [container([section(text)])]
            await send_components(self.bot, ctx.channel.id, comps)
        else:
            await send_error(self.bot, ctx.channel.id, "Transferência Falhou", mensagem)

    @commands.command(name='apostar')
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def cmd_apostar(self, ctx: commands.Context, valor: int):
        """🎰 Aposta moedas. 45% de chance de dobrar! Uso: !apostar <valor>"""
        if valor <= 0:
            await send_error(self.bot, ctx.channel.id, "Aposta Numérica Incorreta", "O valor apostado precisa ser maior que 0!")
            return
        if valor > 10000:
            await send_error(self.bot, ctx.channel.id, "Teto Atingido", "A aposta máxima permitida é de **10.000 OC**")
            return

        await db.get_or_create_user(ctx.author.id, ctx.author.display_name)
        saldo = await db.get_balance(ctx.author.id)
        if saldo < valor:
            await send_error(self.bot, ctx.channel.id, "Saldo Insuficiente", f"Você não tem os fundos. Saldo atual: **{saldo:,} {COIN_SYMBOL}**.")
            return

        ganhou = random.random() < 0.45
        wfire = emoji("wFire", "🎰")
        wcash = emoji("wCash", "💰")
        
        if ganhou:
            premio = valor
            sucesso, novo_saldo = await db.add_coins(ctx.author.id, premio, f"Aposta ganha (+{premio})")
            if not sucesso:
                await send_error(self.bot, ctx.channel.id, "Erro no Banco", "Falha crítica ao processar o seu prêmio.")
                return
            text = (
                f"**{wfire} VOCÊ GANHOU! 🎉**\n\n"
                f"• Apostou: `{valor:,} {COIN_SYMBOL}` → Dobrou!\n"
                f"• +`{premio:,} {COIN_SYMBOL}`\n"
                f"• Saldo: `{novo_saldo:,} {COIN_SYMBOL}`"
            )
        else:
            sucesso, novo_saldo = await db.remove_coins(ctx.author.id, valor, f"Aposta perdida (-{valor})")
            if not sucesso:
                await send_error(self.bot, ctx.channel.id, "Erro no Banco", "Falha de execução ao debitar o seu valor.")
                return
            text = (
                f"**{wcash} Você perdeu... 😢**\n\n"
                f"• Apostou: `{valor:,} {COIN_SYMBOL}` → Perdeu tudo.\n"
                f"• -`{valor:,} {COIN_SYMBOL}`\n"
                f"• Saldo: `{novo_saldo:,} {COIN_SYMBOL}`"
            )
            
        text += "\n\n-# Chance de ganhar: 45%"
        comps = [container([section(text)])]
        await send_components(self.bot, ctx.channel.id, comps)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
