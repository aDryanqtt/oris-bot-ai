"""
Cog AWS Tools — Monitoramento do servidor AWS (CPU, RAM, GPU, Disco, Rede).
Comandos sensíveis são admin-only.
"""

import discord
from discord.ext import commands
import psutil
import platform
import subprocess
import logging

from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis
from utils.helpers import format_bytes, format_uptime
from utils.permissions import admin_only
from config import now_br

logger = logging.getLogger(__name__)


async def send_admin_msg(bot, channel_id, title, msg, is_error=False, icon=None, fallback=""):
    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "🛑") if is_error else emoji("wCheck", "✅"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])])


class AWSToolsCog(commands.Cog, name="☁️ AWS Tools"):
    """Ferramentas de monitoramento do servidor AWS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = now_br()

    def _get_gpu_info(self) -> dict:
        """Obtém info da GPU via nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                parts = [p.strip() for p in result.stdout.strip().split(',')]
                if len(parts) >= 6:
                    return {
                        "name": parts[0],
                        "memory_total": f"{parts[1]} MiB",
                        "memory_used": f"{parts[2]} MiB",
                        "memory_free": f"{parts[3]} MiB",
                        "gpu_util": f"{parts[4]}%",
                        "temp": f"{parts[5]}°C"
                    }
        except Exception as e:
            logger.error(f"Erro nvidia-smi: {e}")
        return {}

    def _get_gpu_processes(self) -> str:
        """Lista processos usando a GPU."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid,name,used_memory",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                procs = []
                for line in lines[:10]:
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 3:
                        procs.append(f"• PID {parts[0]} | {parts[1]} | {parts[2]} MiB")
                return '\n'.join(procs) if procs else "Nenhum processo na GPU"
        except Exception:
            pass
        return "Não disponível"

    @commands.command(name='server')
    @admin_only()
    async def cmd_server(self, ctx: commands.Context):
        """☁️ Status completo do servidor AWS. 🔒 Admin"""
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        boot_time = psutil.boot_time()
        from datetime import datetime
        uptime_secs = (datetime.utcnow() - datetime.utcfromtimestamp(boot_time)).total_seconds()
        gpu = self._get_gpu_info()

        cpu_bar = self._progress_bar(cpu_percent)
        ram_bar = self._progress_bar(mem.percent)
        disk_bar = self._progress_bar(disk.percent)
        net = psutil.net_io_counters()

        wcloud = emoji("wCloud", "☁️")
        lines = [f"**{wcloud} AWS Cloud Monitoring**\n\n"]
        lines.append(f"**🔲 Processador (CPU)**\n{cpu_bar} `{cpu_percent}%`\n• {cpu_count} cores | {platform.processor() or platform.machine()}\n")
        lines.append(f"**🧠 Memória (RAM)**\n{ram_bar} `{mem.percent}%`\n• {format_bytes(mem.used)} / {format_bytes(mem.total)}\n")
        lines.append(f"**💾 Armazenamento**\n{disk_bar} `{disk.percent}%`\n• {format_bytes(disk.used)} / {format_bytes(disk.total)}\n")

        if gpu:
            lines.append(f"**🎮 GPU — {gpu.get('name', 'N/A')}**\n• Uso: `{gpu.get('gpu_util', '?')}` | Temp: `{gpu.get('temp', '?')}`\n• VRAM: `{gpu.get('memory_used', '?')} / {gpu.get('memory_total', '?')}`\n")

        lines.append(f"**🌐 Tráfego Lógico**\n• ↑ `{format_bytes(net.bytes_sent)}` | ↓ `{format_bytes(net.bytes_recv)}`\n")
        lines.append(f"**⏱️ Sessão System**\n• Uptime: `{format_uptime(uptime_secs)}` | Sistema: `{platform.system()} {platform.release()}`\n")

        comps = [container([section("".join(lines)[:4000]), text_display("-# Diagnóstico Gerado em Tempo Real")])]
        await send_components(self.bot, ctx.channel.id, comps)

    @commands.command(name='gpu')
    @admin_only()
    async def cmd_gpu(self, ctx: commands.Context):
        """🎮 Info detalhada da GPU. 🔒 Admin"""
        gpu = self._get_gpu_info()
        if not gpu:
            await send_admin_msg(self.bot, ctx.channel.id, "Placa Dedicada Indisponível", "O utilitário nvidia-smi falhou ou o node carece de GPU dedicada.", True)
            return

        procs = self._get_gpu_processes()

        wfire = emoji("wFire", "🎮")
        text = (
            f"**{wfire} Dedicated Graphics — {gpu.get('name', 'N/A')}**\n\n"
            f"**Carga de Stress:** `{gpu.get('gpu_util', '?')}`\n"
            f"**Termometria (Temp):** `{gpu.get('temp', '?')}`\n\n"
            f"**Alocação de VRAM**\n"
            f"• Consumida: `{gpu.get('memory_used', '?')}`\n"
            f"• Disponível: `{gpu.get('memory_free', '?')}`\n"
            f"• Absoluta: `{gpu.get('memory_total', '?')}`\n\n"
            f"**PID's Computando**\n{procs}"
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name='processos')
    @admin_only()
    async def cmd_processos(self, ctx: commands.Context, n: int = 10):
        """📊 Top processos por uso de recursos. 🔒 Admin. Uso: !processos [n]"""
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)
        top = procs[:min(n, 15)]

        lines = [f"**{emoji('wList', '📊')} Tabela de Tarefas ({len(top)} apps)**\n"]
        for p in top:
            lines.append(
                f"`{p['pid']:>6}` | **{(p['name'] or 'N/A')[:20]:<20}**\n"
                f"↳ CPU: `{p.get('cpu_percent', 0):>5.1f}%` | RAM: `{p.get('memory_percent', 0):>5.1f}%`\n"
            )

        text = "\n".join(lines) if len(lines) > 1 else "**📊 Zero Processos Alcançáveis**"
        await send_components(self.bot, ctx.channel.id, [container([section(text[:4000])])])

    @commands.command(name='disco')
    @admin_only()
    async def cmd_disco(self, ctx: commands.Context):
        """💾 Uso detalhado de disco. 🔒 Admin"""
        partitions = psutil.disk_partitions()

        lines = [f"**{emoji('wFolder', '💾')} Armazenamento de Volumes (EBS/NVME)**\n\n"]
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                bar = self._progress_bar(usage.percent)
                lines.append(f"**Mount: `{part.device}` ({part.mountpoint})**")
                lines.append(f"{bar} `{usage.percent}%`")
                lines.append(f"• Ocupado: `{format_bytes(usage.used)}` / Livre: `{format_bytes(usage.free)}`")
                lines.append(f"• Capacidade Bruta: `{format_bytes(usage.total)}` | FS: `{part.fstype}`\n")
            except (PermissionError, OSError):
                continue

        await send_components(self.bot, ctx.channel.id, [container([section("".join(lines)[:4000])])])

    @commands.command(name='rede')
    @admin_only()
    async def cmd_rede(self, ctx: commands.Context):
        """🌐 Estatísticas de rede. 🔒 Admin"""
        net = psutil.net_io_counters()

        wlink = emoji("wLink", "🌐")
        text = (
            f"**{wlink} Tráfego Externo (I/O)**\n\n"
            f"**Banda Consumida**\n"
            f"• Upload (Tx): `{format_bytes(net.bytes_sent)}`\n"
            f"• Download (Rx): `{format_bytes(net.bytes_recv)}`\n\n"
            f"**Transmissões Handled**\n"
            f"• Tx Pacotes: `{net.packets_sent:,}`\n"
            f"• Rx Pacotes: `{net.packets_recv:,}`\n\n"
            f"**Saúde da Placa**\n"
            f"• Tx Erros: `{net.errout}`\n"
            f"• Rx Erros: `{net.errin}`"
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name='uptime')
    @admin_only()
    async def cmd_uptime(self, ctx: commands.Context):
        """⏱️ Tempo online do servidor e do bot. 🔒 Admin"""
        boot_time = psutil.boot_time()
        from datetime import datetime
        server_uptime = (datetime.utcnow() - datetime.utcfromtimestamp(boot_time)).total_seconds()
        bot_uptime = (now_br() - self.start_time).total_seconds()

        text = (
            f"**{emoji('wClock', '⏱️')} Registro de Uptime**\n\n"
            f"• **Servidor Host:** `{format_uptime(server_uptime)}`\n"
            f"• **Oris Engine:** `{format_uptime(bot_uptime)}`\n\n"
            f"-# Inicializado originalmente em: {datetime.utcfromtimestamp(boot_time).strftime('%d/%m/%Y %H:%M UTC')}"
        )
        await send_components(self.bot, ctx.channel.id, [container([section(text)])])

    @commands.command(name='logs')
    @admin_only()
    async def cmd_logs(self, ctx: commands.Context, n: int = 20):
        """📄 Últimas N linhas do log do bot. 🔒 Admin. Uso: !logs [n]"""
        n = min(n, 50)
        try:
            with open('bot_debug.log', 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-n:]
                content = ''.join(last_lines)

                if len(content) > 1900:
                    content = content[-1900:]

                await ctx.send(f"```\n{content}\n```")
        except FileNotFoundError:
            await send_admin_msg(self.bot, ctx.channel.id, "Leitura Falhou", "Arquivo de syslog (bot_debug.log) não foi encontrado no workspace host.", True)

    @staticmethod
    def _progress_bar(percent: float, length: int = 10) -> str:
        """Cria uma barra de progresso visual."""
        filled = int(length * percent / 100)
        empty = length - filled
        if percent >= 90:
            emoji = "🔴"
        elif percent >= 70:
            emoji = "🟡"
        else:
            emoji = "🟢"
        return f"{emoji} {'█' * filled}{'░' * empty}"


async def setup(bot: commands.Bot):
    await bot.add_cog(AWSToolsCog(bot))
