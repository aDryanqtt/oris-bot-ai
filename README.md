# OrisBot AI

Bot de Discord focado em suporte inteligente para a Oris Cloud, com atendimento por IA, handoff para equipe humana, monitoramento operacional e utilidades para a staff.

## Objetivo

O Oris foi projetado para operar dentro de um servidor Discord como:

- assistente de atendimento com IA contextual
- apoio a tickets e canais de suporte
- camada de consulta sobre serviços da Oris Cloud
- painel operacional para monitorar bot, modelo de IA e ambiente host

## Recursos principais

- Chat com IA via Mistral ou Ollama
- Histórico persistente por usuário e canal
- Análise de links e imagens
- Transferência de tickets para atendimento humano
- Monitoramento de saúde do bot e do provedor de IA
- Ferramentas administrativas, moderação, perfil, lembretes e economia

## Requisitos

- Python 3.11+
- Token de bot do Discord
- Um dos provedores de IA abaixo:
  - Mistral API
  - Ollama local

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

No Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuração

Crie um arquivo `.env` a partir de `.env.example` e preencha os valores reais.

Campos principais:

- `DISCORD_TOKEN`
- `BOT_PREFIX`
- `AI_PROVIDER`
- `MISTRAL_API_KEY`
- `MISTRAL_MODEL`
- `MISTRAL_VISION_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `VISION_MODEL`

## Execução local

```bash
python bot.py
```

Opcionalmente, no Windows, você pode usar `INICIAR_BOT.bat`.

## Estrutura publicada

Esta publicação inicial inclui somente código, scripts, documentação e assets versionáveis. Arquivos sensíveis, logs, ambiente virtual e banco local ficam fora do repositório.
