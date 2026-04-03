"""
Cog Fun & Games — Diversão e jogos casuais.
"""

import discord
from discord.ext import commands
import random
import string
import logging

from utils.ollama_client import ollama
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis

logger = logging.getLogger(__name__)

async def send_error(bot, channel_id, title, erro_msg):
    werror = emoji("wCancel", "🛑")
    text = f"**{werror} {parse_emojis(title)}**\n\n{parse_emojis(erro_msg)}"
    await send_components(bot, channel_id, [container([section(text)])])

async def send_fun(bot, channel_id, title, content, icon="wGame", fallback="🎮", footer=None):
    wicon = emoji(icon, fallback)
    comps = [section(f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(content)[:4096]}")]
    if footer:
        comps.append(text_display(f"-# {parse_emojis(footer)}"))
    await send_components(bot, channel_id, [container(comps)])

class FunCog(commands.Cog, name="🎮 Diversão"):
    """Comandos de diversão e jogos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='dado')
    async def cmd_dado(self, ctx: commands.Context, lados: int = 6):
        """🎲 Rola um dado. Uso: !dado [lados]"""
        if lados < 2:
            lados = 6
        if lados > 1000:
            lados = 1000

        resultado = random.randint(1, lados)
        await send_fun(self.bot, ctx.channel.id, "Dado Rolado!", f"**d{lados}** → **{resultado}**", "wDice", "🎲", f"Rolado por {ctx.author.display_name}")

    @commands.command(name='moeda')
    async def cmd_moeda(self, ctx: commands.Context):
        """🪙 Joga uma moeda — cara ou coroa."""
        resultado = random.choice(["🪙 **Cara!**", "👑 **Coroa!**"])
        await send_fun(self.bot, ctx.channel.id, "Moeda Lançada!", resultado, "wCoin", "🪙", f"Lançada por {ctx.author.display_name}")

    @commands.command(name='8ball')
    async def cmd_8ball(self, ctx: commands.Context, *, pergunta: str):
        """🎱 Bola mágica 8. Uso: !8ball <pergunta>"""
        async with ctx.channel.typing():
            prompt = (
                "Aja como uma clássica Bola Mágica 8 (Magic 8-Ball) mística e divina. "
                "Alguém está te fazendo uma pergunta de sim/não ou sobre o futuro. "
                "Responda a pergunta com autoridade divina ou ceticismo, baseando-se no que lê. "
                "Sua resposta deve ter no máximo 2 frases, seja criativo, enigmático ou sarcástico.\n"
                f"Pergunta do mortal: '{pergunta}'"
            )
            resposta_ia, erro = await ollama.generate_simple(prompt)

            if erro or not resposta_ia:
                resposta_Final = "🎱 A névoa mística está densa... tente novamente."
            else:
                resposta_Final = resposta_ia.strip(' "')

        content = f"**A Pergunta:**\n{pergunta[:500]}\n\n**A Previsão:**\n**{resposta_Final}**"
        await send_fun(self.bot, ctx.channel.id, "Bola Mágica 8", content, "wMagic", "🎱", f"Perguntado por {ctx.author.display_name}")

    @commands.command(name='sorteio')
    async def cmd_sorteio(self, ctx: commands.Context, *, opcoes: str):
        """🎰 Sorteia entre opções. Uso: !sorteio opção1, opção2, opção3"""
        lista = [op.strip() for op in opcoes.split(',') if op.strip()]

        if len(lista) < 2:
            await send_error(self.bot, ctx.channel.id, "Sorteio Inválido", "Forneça pelo menos 2 opções separadas por vírgula.\nEx: `!sorteio pizza, hambúrguer, sushi`")
            return

        escolhida = random.choice(lista)
        todas = '\n'.join(f"{':point_right:' if op == escolhida else '•'} {op}" for op in lista)
        content = f"Sorteando entre **{len(lista)}** opções...\n\n🏆 **[ {escolhida} ]** venceu!\n\n**Opções:**\n{todas[:1024]}"
        await send_fun(self.bot, ctx.channel.id, "Sorteio!", content, "wTrophy", "🎰", f"Sorteado por {ctx.author.display_name}")

    @commands.command(name='senha')
    async def cmd_senha(self, ctx: commands.Context, tamanho: int = 16):
        """🔐 Gera uma senha segura. Uso: !senha [tamanho]"""
        if tamanho < 8: tamanho = 8
        if tamanho > 64: tamanho = 64

        chars = string.ascii_letters + string.digits + "!@#$%&*_-+="
        senha = ''.join(random.SystemRandom().choice(chars) for _ in range(tamanho))

        try:
            dm = await ctx.author.create_dm()
            text = f"**🔐 Senha Gerada**\n\n```\n{senha}\n```\n• Tamanho: **{tamanho} caracteres**\n• Composição: Letras, números e símbolos\n\n-# ⚠️ Copie e guarde em local seguro!"
            await send_components(self.bot, dm.id, [container([section(text)])])
            
            # Avisa no canal público usando container
            aviso = f"**{emoji('wLock', '🔐')} Senha Envida**\n\n{ctx.author.mention}, enviei a senha gerada diretamente na sua DM por segurança!"
            await send_components(self.bot, ctx.channel.id, [container([section(aviso)])])
        except discord.Forbidden:
            aviso = f"**{emoji('wLock', '🔐')} Senha Gerada**\n\nEu não consegui acessar sua DM! Segue a senha abaixo:\n||`{senha}`||\n(clique para revelar)\n\n-# ⚠️ Copie e apague essa mensagem rápido!"
            await send_components(self.bot, ctx.channel.id, [container([section(aviso)])])

    @commands.command(name='emoji')
    async def cmd_emoji(self, ctx: commands.Context, *, texto: str):
        """🔤 Transforma texto em emojis. Uso: !emoji <texto>"""
        emoji_map = {
            'a': '🇦', 'b': '🇧', 'c': '🇨', 'd': '🇩', 'e': '🇪',
            'f': '🇫', 'g': '🇬', 'h': '🇭', 'i': '🇮', 'j': '🇯',
            'k': '🇰', 'l': '🇱', 'm': '🇲', 'n': '🇳', 'o': '🇴',
            'p': '🇵', 'q': '🇶', 'r': '🇷', 's': '🇸', 't': '🇹',
            'u': '🇺', 'v': '🇻', 'w': '🇼', 'x': '🇽', 'y': '🇾',
            'z': '🇿', '0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣',
            '4': '4️⃣', '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣',
            '9': '9️⃣', '!': '❗', '?': '❓', ' ': '  ',
        }
        resultado = ' '.join(emoji_map.get(c.lower(), c) for c in texto[:50])
        await ctx.send(resultado[:2000])

    @commands.command(name='rps')
    async def cmd_rps(self, ctx: commands.Context, escolha: str):
        """✊ Pedra, papel ou tesoura. Uso: !rps <pedra|papel|tesoura>"""
        aliases = {
            'pedra': 'pedra', 'rock': 'pedra', 'p': 'pedra', '✊': 'pedra',
            'papel': 'papel', 'paper': 'papel', 'pa': 'papel', '✋': 'papel',
            'tesoura': 'tesoura', 'scissors': 'tesoura', 't': 'tesoura', '✌️': 'tesoura',
        }

        player = aliases.get(escolha.lower())
        if not player:
            await send_error(self.bot, ctx.channel.id, "Jokenpô Inválido", "Escolha: `pedra`, `papel` ou `tesoura`\nEx: `!rps pedra`")
            return

        bot_choice = random.choice(['pedra', 'papel', 'tesoura'])
        emojis = {'pedra': '✊', 'papel': '✋', 'tesoura': '✌️'}

        if player == bot_choice:
            resultado = "🤝 **Empate!** Ninguém venceu."
        elif (player == 'pedra' and bot_choice == 'tesoura') or \
             (player == 'papel' and bot_choice == 'pedra') or \
             (player == 'tesoura' and bot_choice == 'papel'):
            resultado = "🎉 **Você venceu!** Que habilidade."
        else:
            resultado = "😎 **A IA Venceu!** Tente de novo, humano."

        content = f"{resultado}\n\n**Você** jogou {emojis[player]} {player.title()}\n**Oris** jogou {emojis[bot_choice]} {bot_choice.title()}"
        await send_fun(self.bot, ctx.channel.id, "Jokenpô!", content, "wGame", "🕹️")

    @commands.command(name='roll')
    async def cmd_roll(self, ctx: commands.Context, *, formula: str = "1d20"):
        """🎲 Rola dados no formato NdX. Uso: !roll 2d6, !roll 3d20"""
        import re
        match = re.match(r'^(\d{1,3})d(\d{1,4})$', formula.strip())
        if not match:
            await send_error(self.bot, ctx.channel.id, "Formato Inválido", "Use o padrão `NdX`.\nEx: `!roll 2d6`, `!roll 1d20`")
            return

        n_dados = min(int(match.group(1)), 100)
        lados = min(int(match.group(2)), 1000)

        if n_dados < 1 or lados < 2:
            await send_error(self.bot, ctx.channel.id, "Limite Abusivo", "Mínimo permitido: 1d2")
            return

        resultados = [random.randint(1, lados) for _ in range(n_dados)]
        total = sum(resultados)

        content = f"**Dados Rolados ({n_dados}x):**\n"
        if n_dados <= 20:
            content += ' + '.join(f'**{r}**' for r in resultados) + "\n\n"
        else:
            content += f"*(Muitos dados para listar individualmente...)*\n\n"
            
        content += f"📈 **Soma Total:** {total}\n"
        content += f"📊 **Média Aritmética:** {total/n_dados:.1f}"

        await send_fun(self.bot, ctx.channel.id, f"Rolagem {n_dados}d{lados}", content, "wDice", "🎲", f"Rolado por {ctx.author.display_name}")


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
