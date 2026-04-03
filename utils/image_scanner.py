"""
Scanner de imagens em tempo real para automoderação Cloud.
Converte mídia em fluxo e aciona os workers locais.
"""

import base64
import aiohttp
import discord
import logging
from utils.ollama_client import ollama

logger = logging.getLogger(__name__)

async def scan_attachment_nsfw(attachment: discord.Attachment) -> bool:
    """
    Baixa o anexo na memória RAM, converte para base64 e envia para análise local no Ollama (LLaVA).
    Retorna True se for conteúdo NSFW/Pornográfico/Proibido.
    """
    # Apenas tenta analisar se for uma imagem
    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        return False
        
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    logger.warning(f"Scanner falhou ao baixar imagem: Status {resp.status}")
                    return False
                image_data = await resp.read()
                
        # Converte para string Base64 UTF-8 que o backend do Ollama entende
        base64_img = base64.b64encode(image_data).decode('utf-8')
        
        logger.info(f"Escaneando imagem {attachment.filename} no modelo vision...")
        is_nsfw = await ollama.analyze_image_nsfw(base64_img)
        
        if is_nsfw:
            logger.warning(f"🚨🚨 ALERTA AUTO-MOD: Imagem NSFW bloqueada! ({attachment.filename})")
            
        return is_nsfw
        
    except Exception as e:
        logger.error(f"Erro inesperado no Image Scanner: {e}")
        return False
