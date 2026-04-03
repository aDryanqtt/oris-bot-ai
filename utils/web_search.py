"""
Motor de Pesquisa Web do Oris — Raspagem direta do DuckDuckGo HTML.
Usa aiohttp + BeautifulSoup (já instalados) para máxima estabilidade.
"""
import aiohttp
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def search_web(query: str, max_results: int = 3) -> str:
    """Busca informações na internet via DuckDuckGo HTML (sem dependências extras)."""
    if not query:
        return ""

    logger.info(f"🔍 Pesquisa web iniciada para: '{query}'")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SEARCH_URL,
                data={"q": query, "b": ""},
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"DDG retornou status {resp.status}")
                    return ""

                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        results_text = ""
        count = 0

        for result in soup.select(".result"):
            if count >= max_results:
                break

            title_tag = result.select_one(".result__a")
            snippet_tag = result.select_one(".result__snippet")
            url_tag = result.select_one(".result__url")

            title = title_tag.get_text(strip=True) if title_tag else ""
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            url = url_tag.get_text(strip=True) if url_tag else ""

            if title and snippet:
                count += 1
                results_text += f"[{count}] {title}\nFonte: {url}\nConteúdo: {snippet}\n\n"

        if results_text:
            logger.info(f"✅ {count} resultados encontrados para '{query}'")
        else:
            logger.warning(f"⚠️ Nenhum resultado encontrado para '{query}'")

        return results_text.strip()

    except aiohttp.ClientError as e:
        logger.error(f"Erro de conexão na pesquisa: {e}")
        return ""
    except Exception as e:
        logger.error(f"Erro inesperado na pesquisa web: {e}")
        return ""
