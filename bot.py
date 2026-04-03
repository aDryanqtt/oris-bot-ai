"""
Bot de Discord Assistente de IA Autonomo.
"""

import asyncio
import logging
import os
import sys

# Configura encoding para Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import discord
from discord.ext import commands

from config import DISCORD_TOKEN, BOT_PREFIX, ACTIVE_MODEL, AI_PROVIDER, now_br


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_debug.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot")


intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True
intents.presences = True

bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    help_command=None,
)


COGS = [
    "cogs.chat",
    "cogs.aws_tools",
    "cogs.code_tools",
    "cogs.cloud_gaming",
    "cogs.utilities",
    "cogs.moderation",
    "cogs.system_monitor",
    "cogs.channel_analyzer",
    "cogs.fun",
    "cogs.economy",
    "cogs.reminders",
    "cogs.profile",
    "cogs.tickets",
]


@bot.event
async def on_ready():
    """Evento executado quando o bot esta pronto."""
    logger.info(f'{"=" * 50}')
    logger.info(f"🤖 Bot conectado como {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"🧠 Modelo: {ACTIVE_MODEL}")
    logger.info(f"📡 Servidores: {len(bot.guilds)}")
    logger.info(f"⚙️ Cogs: {len(bot.cogs)}")
    logger.info(f"📝 Comandos: {len(bot.commands)}")
    logger.info(f"🕐 Horario de Brasilia: {now_br().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info(f'{"=" * 50}')

    provider_label = "Mistral" if AI_PROVIDER == "mistral" else "Ollama"
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name=f"{provider_label}: {ACTIVE_MODEL} | {BOT_PREFIX}ajuda",
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)


def _is_admin_command(cmd) -> bool:
    """Verifica se um comando tem check de admin."""
    for check in cmd.checks:
        if hasattr(check, "__qualname__") and "admin" in check.__qualname__.lower():
            return True
    return False


def _render_command_tree(cmd, depth: int = 0) -> list[str]:
    """Renderiza um comando e seus subcomandos para o painel de ajuda."""
    if getattr(cmd, "hidden", False):
        return []

    pad = "  " * depth
    usage = f"{BOT_PREFIX}{cmd.qualified_name}"
    signature = getattr(cmd, "signature", "").strip()
    if signature:
        usage = f"{usage} {signature}"

    summary = (getattr(cmd, "short_doc", None) or cmd.help or "Sem descricao").splitlines()[0].strip()
    lock = " 🔒" if _is_admin_command(cmd) else ""

    lines = [f"{pad}• `{usage}`{lock} — {summary}"]
    if isinstance(cmd, commands.Group):
        for sub in cmd.commands:
            lines.extend(_render_command_tree(sub, depth + 1))
    return lines


COG_EMOJI_MAP = {
    "Chat": "wStream",
    "AWS Tools": "wCloud",
    "Code Tools": "wPy",
    "Utilitarios": "wFix2",
    "Tickets": "wTicket",
    "Moderacao": "wShield",
    "Perfil": "wUser",
    "Economia": "wCash",
    "Lembretes": "wTimer",
    "System Monitor": "wAlert",
    "Fun": "wHello",
    "Emojis": "wEmbed",
    "Analyzer": "Google",
}


def _build_help_select_options(author_id: int) -> tuple:
    """Constroi as opcoes do select e o custom_id com ID do dono."""
    from utils.containers import select_option

    custom_id = f"oris_help:{author_id}"
    options = [select_option("Visao Geral", "visao_geral", "Pagina inicial do assistente", "wInfo")]

    for cog_name, cog in bot.cogs.items():
        if cog.get_commands():
            clean = cog_name
            if " " in cog_name and not cog_name[0].isalnum():
                clean = " ".join(cog_name.split()[1:])
            desc = (cog.description or "Visualizar comandos")[:50]
            emo_key = COG_EMOJI_MAP.get(clean, "wInfo")
            options.append(select_option(clean, cog_name, desc, emo_key))

    return custom_id, options[:25]


def _build_overview_container(author_name: str, author_id: int) -> list:
    """Constroi o container principal da visao geral."""
    from utils.containers import container, section, separator, action_row, string_select, text_display, e

    winfo = e("wInfo", "INFO")
    wuser = e("wUser", "BOT")
    wfire = e("wFire", "HOT")
    warrow = e("wArrow", "->")

    avatar_url = str(bot.user.display_avatar.url) if bot.user else None
    header = (
        f"**{winfo} Central de Intelligence - Oris IA**\n\n"
        f"Bem-vindo ao painel centralizado. {wuser}\n"
        f"**Modelo Ativo:** `{ACTIVE_MODEL}` | **Prefixo:** `{BOT_PREFIX}`\n\n"
        f"**{wfire} Dicas Rapidas:**\n"
        f"• Me mencione no chat para interagir com a inteligencia.\n"
        f"• Mensagens e imagens protegidas via AutoMod Cloud.\n\n"
        f"{warrow} **Use o drop-down abaixo para acessar os modulos.**"
    )

    custom_id, options = _build_help_select_options(author_id)
    return [container([
        section(header, avatar_url),
        separator(),
        action_row(string_select(custom_id, "Selecione um modulo para investigar...", options)),
        text_display(f"-# Sessao de {author_name}"),
    ])]


def _build_module_container(cog_name: str, cog, author_id: int) -> list:
    """Constroi o container de detalhes de um modulo."""
    from utils.containers import container, section, separator, action_row, string_select, text_display, e

    winfo = e("wInfo", "INFO")
    wlock = e("wLocked", "LOCK")

    clean = cog_name
    if " " in cog_name and not cog_name[0].isalnum():
        clean = " ".join(cog_name.split()[1:])

    avatar_url = str(bot.user.display_avatar.url) if bot.user else None
    lines = [f"**{winfo} Modulo: {clean}**\n"]
    lines.append(f"*{cog.description or 'Painel detalhado de funcoes'}*\n")

    for cmd in cog.get_commands():
        for line in _render_command_tree(cmd):
            if "🔒" in line:
                line = line.replace("🔒", wlock)
            lines.append(line)

    custom_id, options = _build_help_select_options(author_id)
    return [container([
        section("\n".join(lines), avatar_url),
        separator(),
        action_row(string_select(custom_id, "Selecione um modulo para investigar...", options)),
        text_display(f"-# {wlock} = Requer privilegio de Administrador"),
    ])]


@bot.command(name="ajuda")
async def cmd_ajuda(ctx: commands.Context):
    """Central de ajuda interativa."""
    from utils.containers import send_components

    components = _build_overview_container(ctx.author.display_name, ctx.author.id)
    await send_components(bot, ctx.channel.id, components)


@bot.listen("on_interaction")
async def handle_help_select(interaction: discord.Interaction):
    """Handler global para o dropdown de ajuda."""
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
    if not custom_id.startswith("oris_help:"):
        return

    try:
        owner_id = int(custom_id.split(":")[1])
    except (IndexError, ValueError):
        return

    if interaction.user.id != owner_id:
        await interaction.response.send_message(
            "🛑 Este menu pertence a outro usuario. Execute `!ajuda` voce mesmo.",
            ephemeral=True,
        )
        return

    from utils.containers import edit_interaction

    await interaction.response.defer()

    selected = interaction.data.get("values", [None])[0]
    if not selected:
        return

    try:
        if selected == "visao_geral":
            components = _build_overview_container(interaction.user.display_name, owner_id)
        else:
            components = None
            for cog_name, cog in bot.cogs.items():
                if cog_name == selected:
                    components = _build_module_container(cog_name, cog, owner_id)
                    break
            if components is None:
                return

        await edit_interaction(bot, interaction.token, components)
    except Exception as exc:
        logger.error(f"Erro ao processar selecao do !ajuda: {exc}", exc_info=exc)


@bot.check
async def global_channel_check(ctx: commands.Context):
    """Bloqueia comandos fora do canal configurado."""
    if ctx.guild is None:
        return True

    if _is_admin_command(ctx.command) or ctx.author.guild_permissions.administrator or ctx.author.id == 666739489502396438:
        return True

    from utils.database import db

    bot_channel_id = await db.get_bot_channel(ctx.guild.id)
    if bot_channel_id and ctx.channel.id != bot_channel_id:
        try:
            await ctx.message.delete(delay=2)
            await ctx.author.send(f"⚠️ Por favor, use meus comandos apenas no canal <#{bot_channel_id}>.")
        except Exception:
            pass
        return False

    return True


@bot.event
async def on_command_error(ctx: commands.Context, error):
    """Tratamento global de erros."""
    from utils.embed_builder import get_emoji

    wcancel = get_emoji("wCancel", "X")
    wtimer = get_emoji("wTimer", "TIME")

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=discord.Embed(
            title=f"{wcancel} Argumento faltando",
            description=f"Uso correto: `{BOT_PREFIX}{ctx.command.name} {ctx.command.signature}`\n\nUse `{BOT_PREFIX}ajuda` para mais informacoes.",
            color=0x000000,
        ))
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(embed=discord.Embed(
            title=f"{wtimer} Cooldown",
            description=f"Aguarde **{error.retry_after:.1f}s** antes de usar este comando novamente.",
            color=0x000000,
        ))
    elif isinstance(error, commands.CheckFailure):
        pass
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=discord.Embed(
            title=f"{wcancel} Membro nao encontrado",
            description="Nao consegui encontrar o membro especificado. Verifique o ID ou a mencao.",
            color=0x000000,
        ))
    else:
        logger.error(f"Erro no comando {ctx.command}: {error}", exc_info=error)
        await ctx.send(embed=discord.Embed(
            title=f"{wcancel} Erro inesperado",
            description=f"```{str(error)[:1000]}```",
            color=0x000000,
        ))


async def load_cogs():
    """Carrega todos os cogs."""
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as exc:
            logger.error(f"❌ Erro ao carregar {cog}: {exc}", exc_info=exc)


async def main():
    """Funcao principal assincrona."""
    logger.info("=" * 50)
    logger.info("🚀 INICIANDO BOT ORIS - IA CLOUD")
    logger.info("=" * 50)

    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN nao encontrado no .env!")
        return

    from utils.database import db
    from utils.ollama_client import ollama

    await db.connect()
    logger.info("✅ Banco de dados inicializado")

    try:
        async with bot:
            await load_cogs()
            logger.info("🔗 Conectando ao Discord...")
            await bot.start(DISCORD_TOKEN)
    finally:
        try:
            await ollama.close()
        except Exception as exc:
            logger.warning(f"Falha ao fechar sessao HTTP da IA: {exc}")
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Bot encerrado pelo usuario.")
    except Exception as exc:
        logger.error(f"💥 Erro fatal: {exc}", exc_info=exc)
