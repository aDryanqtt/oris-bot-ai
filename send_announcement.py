"""
Script único para enviar o anúncio do Bot Oris no canal de anúncios.
Usa Embed do Discord (suporta até 6000 chars) para contornar o limite de 2000 chars.
"""
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = "1483346344616656926"

EMBED = {
    "title": "🤖 Apresentando: Oris — Sua IA Assistente do Servidor!",
    "description": (
        "*Inteligência Artificial de verdade, rodando 24/7, direto no seu Discord.*\n\n"
        "Fala, comunidade! Venho anunciar oficialmente o nosso mais novo membro: "
        "o **Oris**, um bot de IA completo, desenvolvido do zero por **Z2ky (.zequin)** 🧠⚡\n\n"
        "Ele não é um bot genérico — ele **pensa, pesquisa na internet em tempo real, "
        "lembra das suas conversas** e se adapta ao contexto do servidor."
    ),
    "color": 0x9B59B6,
    "fields": [
        {
            "name": "🗣️ Chat Inteligente",
            "value": "Converse mencionando `@Oris` ou respondendo uma mensagem dele. Ele entende contexto e lembra do histórico!",
            "inline": True
        },
        {
            "name": "🔍 Pesquisa Web em Tempo Real",
            "value": "Pergunte sobre notícias, preços ou lançamentos. Ele acessa a internet automaticamente!",
            "inline": True
        },
        {
            "name": "💰 Sistema de Economia",
            "value": "Ganhe **Oris Coins** com `!daily`, veja seu `!saldo`, suba no `!ranking` e use `!transferir`!",
            "inline": True
        },
        {
            "name": "🛡️ Segurança Anti-Exploit",
            "value": "Blindagem contra Jailbreak e Engenharia Social. Ele **nunca** criará códigos maliciosos.",
            "inline": True
        },
        {
            "name": "🎭 Personas & Perfil",
            "value": "Mude o estilo com `!persona`: programador, professor, humorista, formal ou criativo! Veja seu `!perfil` com XP e nível.",
            "inline": True
        },
        {
            "name": "🔗 Leitura de Links & Canais",
            "value": "Cole um link e ele lê, resume e analisa. Também pode analisar canais do servidor!",
            "inline": True
        },
        {
            "name": "🔒 Privacidade Total",
            "value": "Suas DMs ficam 100% isoladas do servidor. Nada vaza, nada se mistura.",
            "inline": True
        },
        {
            "name": "🎱 8Ball com IA",
            "value": "O clássico `!8ball`, mas com respostas geradas pela IA. Cada resposta é única!",
            "inline": True
        },
        {
            "name": "⏰ Lembretes",
            "value": "`!lembrar 30m estudar` e ele te avisa na hora certa!",
            "inline": True
        },
        {
            "name": "\u200b",
            "value": "\u200b",
            "inline": False
        },
        {
            "name": "🚀 Como Usar?",
            "value": (
                "1️⃣ Mencione `@Oris` em qualquer mensagem ou responda a ele\n"
                "2️⃣ Mande DM direta pra conversas privadas\n"
                "3️⃣ Use `!help` para ver todos os comandos"
            ),
            "inline": False
        },
    ],
    "footer": {
        "text": "Desenvolvido com 💜 por Z2ky (.zequin) • Python + Discord.py + IA Cloud"
    },
    "thumbnail": {
        "url": "https://cdn-icons-png.flaticon.com/512/4712/4712027.png"
    }
}

async def send_announcement():
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "content": "@everyone",
        "embeds": [EMBED]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status in (200, 201):
                print("✅ Anúncio enviado com sucesso no canal!")
            else:
                text = await resp.text()
                print(f"❌ Erro {resp.status}: {text}")

asyncio.run(send_announcement())
