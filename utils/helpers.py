"""
Funções auxiliares — URL fetching, formatação, etc.
"""

import re
import aiohttp
import logging
from typing import Optional
from bs4 import BeautifulSoup
from config import URL_FETCH_TIMEOUT

logger = logging.getLogger(__name__)


async def fetch_url_content(url: str, max_chars: int = 5000) -> tuple[Optional[str], Optional[str]]:
    """
    Busca e extrai texto de uma URL.
    Returns: (conteudo_texto, erro)
    """
    try:
        timeout = aiohttp.ClientTimeout(total=URL_FETCH_TIMEOUT)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    return None, f"HTTP {resp.status}"

                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    html = await resp.text(errors='replace')
                    soup = BeautifulSoup(html, 'html.parser')

                    # Remove scripts, styles, nav, footer
                    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
                        tag.decompose()

                    # Extrai título
                    title = soup.title.string.strip() if soup.title and soup.title.string else "Sem título"

                    # Extrai texto principal
                    text = soup.get_text(separator='\n', strip=True)

                    # Limpa linhas vazias duplicadas
                    lines = [line for line in text.splitlines() if line.strip()]
                    clean_text = '\n'.join(lines)

                    result = f"**Título:** {title}\n\n{clean_text[:max_chars]}"
                    if len(clean_text) > max_chars:
                        result += "\n\n[... conteúdo truncado ...]"

                    return result, None

                elif "text/plain" in content_type:
                    text = await resp.text(errors='replace')
                    return text[:max_chars], None

                elif "application/json" in content_type:
                    text = await resp.text()
                    return f"```json\n{text[:max_chars]}\n```", None

                else:
                    return None, f"Tipo de conteúdo não suportado: {content_type}"

    except aiohttp.ClientError as e:
        return None, f"Erro de conexão: {str(e)}"
    except Exception as e:
        logger.error(f"Erro ao buscar URL {url}: {e}")
        return None, f"Erro: {str(e)}"


def extract_urls(text: str) -> list[str]:
    """Extrai URLs de um texto."""
    url_pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE
    )
    return url_pattern.findall(text)


def split_message(text: str, max_len: int = 1990) -> list[str]:
    """Divide uma mensagem longa em partes que cabem no Discord."""
    if len(text) <= max_len:
        return [text]

    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break

        # Tenta dividir em quebra de linha
        split_pos = text.rfind('\n', 0, max_len)
        if split_pos == -1 or split_pos < max_len // 2:
            # Tenta dividir em espaço
            split_pos = text.rfind(' ', 0, max_len)
        if split_pos == -1:
            split_pos = max_len

        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    return parts


def format_bytes(bytes_val: int) -> str:
    """Formata bytes para unidade legível."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


def format_uptime(seconds: float) -> str:
    """Formata segundos em tempo legível."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")

    return ' '.join(parts)


def truncate(text: str, max_len: int = 1024) -> str:
    """Trunca texto com reticências."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
