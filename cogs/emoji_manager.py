"""
Cog Emoji Manager — Importador autônomo dos arquivos de arte gráfica (.webp).
Puxa os ícones e joga no Discord do dono silenciosamente.
"""

import discord
from discord.ext import commands
import os
import glob
import json
import logging
from config import now_br
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis

logger = logging.getLogger(__name__)

class EmojiManagerCog(commands.Cog, name="🎨 Emojis"):
    """Sincroniza os ícones do sistema para os emojis do servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.emojis_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Emojis")
        
    @commands.command(name='sync_emojis')
    @commands.has_permissions(administrator=True)
    async def cmd_sync_emojis(self, ctx: commands.Context):
        """📥 Instala pacote de emojis premium no servidor. Uso: !sync_emojis"""
        wload = emoji("wClock", "⏳")
        loading = await ctx.send(f"**{wload} Iniciando scanner da pasta raiz de Emojis...**")
        
        webp_files = glob.glob(os.path.join(self.emojis_dir, "*.webp"))
        
        if not webp_files:
            wcanc = emoji("wCancel", "❌")
            await send_components(self.bot, ctx.channel.id, [container([section(f"**{wcanc} Erro do Scanner**\n\nNão encontrei nenhum arquivo `.webp` na pasta raiz de arte `cogs/Emojis`.")])])
            await loading.delete()
            return
            
        emojis_criados = 0
        emojis_ignorados = 0
        
        # Mapeamento do servidor ativo
        existing_emojis = {e.name: str(e) for e in ctx.guild.emojis}
        
        for file_path in webp_files:
            file_name = os.path.basename(file_path)
            emoji_name = os.path.splitext(file_name)[0]
            
            # Limpa o numeral estranho (1428750919184416809.webp) na base local se tiver
            if emoji_name.isdigit():
                emoji_name = "wItem" + emoji_name[-2:]
                
            if emoji_name in existing_emojis:
                emojis_ignorados += 1
                continue
                
            try:
                with open(file_path, "rb") as image:
                    image_bytes = image.read()
                novo_emoji = await ctx.guild.create_custom_emoji(name=emoji_name, image=image_bytes)
                existing_emojis[emoji_name] = str(novo_emoji)
                emojis_criados += 1
                logger.info(f"🎨 Emoji {emoji_name} criado no servidor com sucesso!")
            except Exception as e:
                logger.error(f"Erro ao criar emoji {emoji_name}: {e}")
                
        # Escreve o banco cache de emojis finais
        output_db = os.path.join("data", "emojis.json")
        os.makedirs("data", exist_ok=True)
        try:
            with open(output_db, "w", encoding="utf-8") as f:
                json.dump(existing_emojis, f, indent=4)
        except Exception as e:
            logger.error(f"Falha ao salvar emojis.json: {e}")
            
        wstar = emoji("wStar", "✨")
        text = (
            f"**{wstar} Pacote Premium Sincronizado**\n\n"
            f"• **Arquivos detectados:** `{len(webp_files)}`\n"
            f"• **Emojis Upados:** `{emojis_criados}`\n"
            f"• **Ignorados (já existiam no servidor):** `{emojis_ignorados}`\n\n"
            f"-# (O banco de dados visual da inteligência artificial foi reconstruído. Ela utilizará essas artes daqui pra frente)"
        )
        
        await loading.delete()
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiManagerCog(bot))
