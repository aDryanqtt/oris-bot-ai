"""
Cliente de IA Unificado — Suporta Mistral API (primário) e Ollama (fallback local).
"""

import aiohttp
import asyncio
import json
import logging
from typing import Optional
from config import (
    AI_PROVIDER, MISTRAL_API_KEY, MISTRAL_MODEL, MISTRAL_VISION_MODEL, MISTRAL_API_URL,
    OLLAMA_BASE_URL, OLLAMA_MODEL, VISION_MODEL, AI_TIMEOUT, MAX_RETRIES,
    SYSTEM_PROMPT, PERSONAS, ACTIVE_MODEL
)

logger = logging.getLogger(__name__)


class AIClient:
    """Cliente unificado para Mistral API e Ollama."""

    def __init__(self):
        self.provider = AI_PROVIDER
        self.model = ACTIVE_MODEL
        self._session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT)

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ==================== MISTRAL API ====================

    async def _mistral_chat(self, messages: list, system_prompt: str, model: str = None) -> tuple[Optional[str], Optional[str]]:
        """Chama a API da Mistral."""
        model = model or MISTRAL_MODEL

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        payload = {
            "model": model,
            "messages": full_messages,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 2048,
        }

        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        }

        for attempt in range(MAX_RETRIES + 1):
            try:
                session = await self.get_session()
                async with session.post(
                    MISTRAL_API_URL,
                    json=payload,
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            return content, None
                        return None, "Resposta vazia do modelo."
                    elif resp.status == 429:
                        # Rate limited
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(2)
                            continue
                        return None, "⏳ Rate limit da API. Tente novamente em alguns segundos."
                    elif resp.status == 401:
                        return None, "🔑 API Key inválida. Verifique MISTRAL_API_KEY no .env"
                    else:
                        error_text = await resp.text()
                        logger.error(f"Mistral API status {resp.status}: {error_text}")
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(1)
                            continue
                        return None, f"Erro da API Mistral (status {resp.status})"

            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                return None, "⏱️ Tempo esgotado! A API demorou muito para responder."
            except aiohttp.ClientError as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                return None, f"❌ Erro de conexão: {str(e)}"
            except Exception as e:
                logger.error(f"Erro inesperado Mistral: {type(e).__name__}: {e}")
                return None, f"❌ Erro inesperado: {str(e)}"

        return None, "❌ Falha após múltiplas tentativas."

    # ==================== OLLAMA ====================

    async def _ollama_chat(
        self,
        messages: list,
        system_prompt: str,
        model: str = None,
        options: dict | None = None,
        retries: int | None = None
    ) -> tuple[Optional[str], Optional[str]]:
        """Chama a API local do Ollama."""
        model = model or OLLAMA_MODEL
        retries = MAX_RETRIES if retries is None else retries

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        payload = {
            "model": model,
            "messages": full_messages,
            "stream": False,
            "options": options or {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 2048,
            }
        }

        for attempt in range(retries + 1):
            try:
                session = await self.get_session()
                async with session.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data.get("message", {}).get("content", "")
                        if content:
                            return content, None
                        return None, "Resposta vazia do modelo."
                    else:
                        error_text = await resp.text()
                        logger.error(f"Ollama status {resp.status}: {error_text}")
                        if attempt < retries:
                            await asyncio.sleep(1)
                            continue
                        return None, f"Erro do Ollama (status {resp.status})"

            except asyncio.TimeoutError:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None, "⏱️ Tempo esgotado!"
            except aiohttp.ClientError as e:
                if attempt < retries:
                    await asyncio.sleep(1)
                    continue
                return None, f"❌ Erro de conexão Ollama: {str(e)}"
            except Exception as e:
                logger.error(f"Erro inesperado Ollama: {type(e).__name__}: {e}")
                return None, f"❌ Erro inesperado: {str(e)}"

        return None, "❌ Falha após múltiplas tentativas."

    async def analyze_image_nsfw(self, base64_img: str) -> bool:
        """
        [Cloud AutoMod] Faz bypass do Mistral e utiliza a sua Tesla T4 via Ollama
        (modelo LLaVA) para analisar se a imagem tem teor NSFW ou malicioso.
        """
        messages = [{
            "role": "user",
            "content": "Analyze this image. Does it contain sexually explicit pornography, extreme violence, or highly offensive/NSFW content? Answer ONLY with the word YES or NO. Do not explain.",
            "images": [base64_img]
        }]
        
        # Força model vision e temperature super baixa pra precisão
        res, err = await self._ollama_chat(
            messages,
            "You are a strict cybersecurity and moderation assistant.",
            model=VISION_MODEL,
            options={
                "temperature": 0.1,
                "top_p": 0.3,
                "num_predict": 8,
                "num_ctx": 1024,
            },
            retries=0
        )
        if err or not res:
            logger.error(f"Ollama Image Scanner Error ({VISION_MODEL}): {err}")
            return False
            
        # Limpa pontuação comum
        return "YES" in res.upper()

    async def describe_image(self, base64_img: str, prompt: str = None) -> tuple[Optional[str], Optional[str]]:
        """
        Usa um modelo vision local no Ollama para descrever ou analisar imagens.
        Retorna: (descricao, erro)
        """
        vision_prompt = prompt or (
            "Descreva esta imagem em português do Brasil com foco no que é visível, "
            "texto legível, contexto aparente e detalhes relevantes para responder "
            "perguntas do usuário. Se houver dúvida, deixe isso claro."
        )
        messages = [{
            "role": "user",
            "content": vision_prompt,
            "images": [base64_img]
        }]
        return await self._ollama_chat(
            messages,
            "Você é um assistente de visão computacional preciso e objetivo.",
            model=VISION_MODEL,
            options={
                "temperature": 0.2,
                "top_p": 0.6,
                "num_predict": 96,
                "num_ctx": 1024,
            },
            retries=0
        )

    async def describe_image_url(self, image_url: str, prompt: str = None) -> tuple[Optional[str], Optional[str]]:
        """
        Usa a Mistral Vision quando disponível; cai para erro caso a URL não possa ser analisada.
        Retorna: (descricao, erro)
        """
        vision_prompt = prompt or (
            "Descreva esta imagem em português do Brasil com foco apenas no que é visível. "
            "Se houver incerteza, diga isso claramente."
        )

        if self.provider == 'mistral':
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {"type": "image_url", "image_url": image_url},
                ]
            }]
            return await self._mistral_chat(
                messages,
                "Você é um assistente de visão computacional preciso e objetivo.",
                model=MISTRAL_VISION_MODEL
            )

        return None, "Vision por URL só está configurado para a Mistral."

    # ==================== INTERFACE UNIFICADA ====================

    async def chat(
        self,
        messages: list,
        persona: str = "padrao",
        model_override: str = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Envia mensagens para o provedor de IA ativo.
        Returns: (resposta, erro) — um dos dois será None.
        """
        system_prompt = PERSONAS.get(persona, SYSTEM_PROMPT)

        if self.provider == 'mistral':
            return await self._mistral_chat(messages, system_prompt, model_override)
        else:
            return await self._ollama_chat(messages, system_prompt, model_override)

    async def generate_simple(self, prompt: str, model_override: str = None) -> tuple[Optional[str], Optional[str]]:
        """Geração simples sem histórico — para tarefas unitárias."""
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, model_override=model_override)

    async def is_online(self) -> bool:
        """Verifica se o provedor de IA está acessível."""
        if self.provider == 'mistral':
            try:
                session = await self.get_session()
                headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
                async with session.get("https://api.mistral.ai/v1/models", headers=headers) as resp:
                    return resp.status == 200
            except Exception:
                return False
        else:
            try:
                session = await self.get_session()
                async with session.get(f"{OLLAMA_BASE_URL}/api/tags") as resp:
                    return resp.status == 200
            except Exception:
                return False

    async def list_models(self) -> list:
        """Lista modelos disponíveis."""
        if self.provider == 'mistral':
            try:
                session = await self.get_session()
                headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
                async with session.get("https://api.mistral.ai/v1/models", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("data", [])
            except Exception as e:
                logger.error(f"Erro ao listar modelos Mistral: {e}")
            return []
        else:
            try:
                session = await self.get_session()
                async with session.get(f"{OLLAMA_BASE_URL}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("models", [])
            except Exception as e:
                logger.error(f"Erro ao listar modelos Ollama: {e}")
            return []

    def set_model(self, model: str):
        """Troca o modelo em tempo real."""
        self.model = model

    def set_provider(self, provider: str):
        """Troca o provedor ('mistral' ou 'ollama')."""
        if provider in ('mistral', 'ollama'):
            self.provider = provider
            if provider == 'mistral':
                self.model = MISTRAL_MODEL
            else:
                self.model = OLLAMA_MODEL


# Instância global
ollama = AIClient()
