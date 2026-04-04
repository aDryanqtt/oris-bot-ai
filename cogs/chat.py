"""
Cog de Chat Inteligente — Conversa com IA, personas, DM, análise de links.
Agora com histórico persistente no banco de dados e contexto personalizado.
"""

import discord
from discord.ext import commands
from collections import defaultdict
import logging
import base64
import aiohttp

from utils.ollama_client import ollama
from utils.admin_knowledge import format_admin_knowledge_context, get_relevant_admin_knowledge
from utils.helpers import split_message, extract_urls, fetch_url_content
from utils.database import db
from utils.ticketing import OWNER_ID, STAFF_ROLE_ID, is_staff_member
from utils.ticketing import is_ticket_channel as shared_is_ticket_channel
from utils.ticketing import is_ticket_routing_channel as shared_is_ticket_routing_channel
from utils.web_search import search_web
from utils import channel_knowledge
from config import MAX_HISTORY, PERSONAS, now_br, get_greeting, format_datetime_br
from utils.containers import container, section, text_display, send_components, e as emoji, parse_emojis

logger = logging.getLogger(__name__)

user_personas = defaultdict(lambda: "padrao")

TICKET_INTENT_PROMPT = """Voce classifica mensagens de tickets da Oris Cloud.
Analise a intencao principal do cliente e retorne EXATAMENTE 3 linhas:
INTENT: plano_recomendado | comparacao_planos | revenda | compra_fechamento | suporte_tecnico | outro
CONFIDENCE: HIGH | MEDIUM | LOW
NEXT_STEP: responder | sugerir_ticket_humano | chamar_staff

Regras:
- plano_recomendado: usuario quer saber qual plano faz mais sentido para o uso dele.
- comparacao_planos: usuario compara duracao, custo-beneficio, adicionais ou opcoes.
- revenda: usuario fala de revenda, tabela de revenda, margem ou valores para revender.
- compra_fechamento: usuario quer comprar, gerar PIX, pagar, aprovar pagamento, liberar maquina ou entregar acesso.
- suporte_tecnico: problema tecnico, erro, lag, instabilidade, falha de uso.
- outro: tudo que nao se encaixa.
- NEXT_STEP deve ser chamar_staff para compra_fechamento.
- NEXT_STEP pode ser sugerir_ticket_humano para suporte_tecnico avancado ou situacao pouco clara.
- Se estiver em duvida entre responder e escalar, prefira responder.
"""


async def send_msg(bot, channel_id, title, msg, is_error=False, icon=None, fallback="", ping=None):
    wicon = emoji(icon, fallback) if icon else (emoji("wCancel", "🛑") if is_error else emoji("wCheck", "✅"))
    text = f"**{wicon} {parse_emojis(title)}**\n\n{parse_emojis(msg)}"
    await send_components(bot, channel_id, [container([section(text)])], content=ping)


class ChatCog(commands.Cog, name="💬 Chat"):
    """Sistema de chat inteligente com IA."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.human_tickets = set()
        self.chat_cooldown = commands.CooldownMapping.from_cooldown(1, 7.0, commands.BucketType.user)

    async def _get_history(self, user_id: int, channel_id: int) -> list:
        return await db.get_conversation_history(user_id, channel_id, limit=MAX_HISTORY)

    def _is_ticket_channel(self, channel) -> bool:
        return shared_is_ticket_channel(channel)

    def _is_ticket_routing_channel(self, channel) -> bool:
        return shared_is_ticket_routing_channel(channel)

    def _parse_ticket_intent_result(self, response: str) -> dict | None:
        fields = {}
        for raw_line in response.splitlines():
            line = raw_line.strip()
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip().upper()] = value.strip()

        intent = fields.get("INTENT", "").lower()
        confidence = fields.get("CONFIDENCE", "").upper()
        next_step = fields.get("NEXT_STEP", "").lower()

        if intent not in {
            "plano_recomendado",
            "comparacao_planos",
            "revenda",
            "compra_fechamento",
            "suporte_tecnico",
            "outro",
        }:
            return None
        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            return None
        if next_step not in {"responder", "sugerir_ticket_humano", "chamar_staff"}:
            return None

        return {
            "intent": intent,
            "confidence": confidence,
            "next_step": next_step,
        }

    async def _classify_ticket_intent(self, content: str, channel) -> dict | None:
        text = (content or "").strip()
        if not text or not self._is_ticket_channel(channel):
            return None

        prompt = (
            f"{TICKET_INTENT_PROMPT}\n\n"
            f"Canal: #{getattr(channel, 'name', 'desconhecido')}\n"
            f"Mensagem do cliente:\n\"\"\"\n{text[:1200]}\n\"\"\""
        )
        response, error = await ollama.generate_simple(prompt)
        if error or not response:
            logger.warning(f"Classificacao de ticket falhou: {error or 'resposta vazia'}")
            return None

        parsed = self._parse_ticket_intent_result(response)
        if not parsed:
            logger.warning(f"Classificacao de ticket retornou formato invalido: {response[:300]!r}")
            return None

        return parsed

    def _build_ticket_intent_context(self, ticket_intent: dict | None) -> str:
        if not ticket_intent:
            return ""

        intent = ticket_intent["intent"]
        confidence = ticket_intent["confidence"]
        next_step = ticket_intent["next_step"]

        instructions = [
            "[=== CLASSIFICACAO DE INTENCAO DO TICKET ===",
            f"Intent principal detectada: {intent}",
            f"Confianca: {confidence}",
            f"Proximo passo preferido: {next_step}",
            "Responda em portugues do Brasil, de forma curta, objetiva e com proximo passo claro.",
            "Nao misture revenda com tabela de planos normais.",
            "Nao invente preco, plano, margem, prazo ou recurso fora da base oficial.",
        ]

        if intent == "plano_recomendado":
            instructions.extend([
                "Entenda o uso do cliente e recomende o plano mais coerente quando houver contexto suficiente.",
                "Se faltar um dado essencial, faca no maximo 1 pergunta objetiva.",
                "Feche a resposta com uma recomendacao pratica.",
            ])
        elif intent == "comparacao_planos":
            instructions.extend([
                "Compare opcoes em no maximo 3 pontos curtos.",
                "Diga qual opcao faz mais sentido no caso descrito.",
                "Feche com uma recomendacao objetiva.",
            ])
        elif intent == "revenda":
            instructions.extend([
                "Use apenas a tabela oficial de revenda.",
                "Se o usuario pedir valores, responda com os valores de revenda sem misturar com plano comum.",
                "Se fizer sentido, indique qual faixa parece melhor para comecar.",
            ])
        elif intent == "compra_fechamento":
            instructions.extend([
                "O cliente ja esta em fase de compra ou liberacao.",
                "Seja curto, confirme o proximo passo humano e inclua [CHAMAR_STAFF].",
                "Nao tente aprovar pagamento nem liberar maquina voce mesmo.",
            ])
        elif intent == "suporte_tecnico":
            instructions.extend([
                "Se for algo simples, responda com orientacao direta.",
                "Se parecer avancado ou depender de equipe, diga isso de forma curta.",
            ])

        if next_step == "sugerir_ticket_humano":
            instructions.append("Sinalize de forma breve que um humano pode precisar assumir se isso nao resolver.")
        elif next_step == "chamar_staff":
            instructions.append("Inclua [CHAMAR_STAFF] na resposta.")

        instructions.append("=== FIM DA CLASSIFICACAO DE INTENCAO ===]")
        return "\n".join(instructions)

    def _build_context(
        self,
        user_name: str,
        channel: discord.abc.GuildChannel,
        roles_text: str = "",
        query: str = "",
    ) -> str:
        hora = now_br()
        saudacao = get_greeting()
        ctx_str = (
            f"\n[SISTEMA - CONTEXTO ATUAL: "
            f"Usuário: {user_name}{roles_text} | "
            f"Horário de Brasília: {format_datetime_br(hora)} | "
            f"Saudação adequada: {saudacao}. "
            f"Trate o usuário de forma imersiva.\n"
            f"REGRA CRÍTICA DE TAMANHO DE TEXTO: Molde o tamanho da sua resposta à pergunta. "
            f"Perguntas simples: Responda em 1 a 2 linhas curtas. "
            f"Explicações completas: MÁXIMO ABSOLUTO de 3 parágrafos curtos. "
            f"EXCEÇÃO: Se o usuário pedir para analisar, criar ou otimizar CÓDIGO de programação, ignore o limite de tamanho e forneça o código completo formatado perfeitamente com crases triplas (```linguagem). "
            f"NÃO vomite toneladas de informações. Entregue apenas o que o usuário pediu.]"
        )

        ctx_str += (
            "\n[PRIORIDADE DE VERDADE: 1) base oficial da Oris Cloud, "
            "2) conhecimento aprovado por admins, 3) contexto relevante de canais publicos. "
            "Se a resposta nao estiver sustentada por essas fontes ou pela mensagem atual, "
            "diga claramente que nao sabe e sugira ticket ou equipe humana.]"
        )

        import os
        kb_path = os.path.join("data", "oris_knowledge.txt")
        kb = None
        if os.path.exists(kb_path):
            try:
                with open(kb_path, "r", encoding="utf-8") as f:
                    kb = f.read()
            except Exception as e:
                logger.error(f"Erro ao ler Knowledge Base: {e}")

        is_ticket = self._is_ticket_channel(channel)

        if is_ticket:
            if kb:
                ctx_str += (
                    f"\n\n[=== MODO SUPORTE ORIS CLOUD ===\n"
                    f"O usuário abriu um ticket. Seja proativo e ajude-o respondendo usando EXATAMENTE nossa documentação abaixo:\n"
                    f"{kb}\n"
                    f"Não mencione que você leu este documento reservado. Fale com naturalidade como Assistente.]\n"
                )
        else:
            if kb:
                ctx_str += (
                    f"\n\n[=== BASE DE CONHECIMENTO OFICIAL ORIS CLOUD ===\n"
                    f"REGRA CRÍTICA: Use APENAS os planos, preços e informações abaixo ao falar sobre a Oris Cloud. "
                    f"NUNCA invente planos, preços, specs ou dados que não estejam explicitamente aqui. "
                    f"Se não souber algo, diga que pode abrir um ticket para o suporte. "
                    f"Fale com naturalidade, sem citar este documento.\n\n"
                    f"{kb}\n"
                    f"=== FIM DA BASE DE CONHECIMENTO OFICIAL ===]\n"
                )

            guild_id = getattr(channel, 'guild', None)
            guild_id = guild_id.id if guild_id else None
            if guild_id:
                canal_ctx = channel_knowledge.get_relevant_context(guild_id, query) if query else channel_knowledge.get_context(guild_id)
                if canal_ctx:
                    ctx_str += (
                        f"\n\n[=== CONTEXTO DO SERVIDOR (canais públicos) ===\n"
                        f"Use as informações abaixo para responder perguntas sobre o servidor, seus serviços ou regras. "
                        f"Fale com naturalidade, sem mencionar que leu os canais.\n\n"
                        f"{canal_ctx}\n"
                        f"=== FIM DO CONTEXTO DO SERVIDOR ===]\n"
                    )

        return ctx_str

    async def _run_vision_reply(self, content: str, attachments: list[discord.Attachment]) -> tuple[str | None, str | None]:
        image_attachments = []
        for attachment in attachments[:3]:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                image_attachments.append(attachment)

        if not image_attachments:
            return None, None

        prompt_base = (
            "Responda em português do Brasil, de forma objetiva, com base apenas no que é visível na imagem. "
            "Se houver incerteza, diga isso claramente. "
            "Não invente contexto externo. "
        )
        if content.strip():
            prompt_base += f"Pergunta do usuário: {content.strip()}"
        else:
            prompt_base += "Descreva de forma curta o que aparece na imagem."

        respostas = []
        if ollama.provider == "mistral":
            for attachment in image_attachments:
                try:
                    descricao, erro = await ollama.describe_image_url(attachment.url, prompt_base)
                    if erro or not descricao:
                        logger.warning(f"Vision falhou em {attachment.filename}: {erro}")
                        continue
                    respostas.append(descricao.strip())
                except Exception as e:
                    logger.error(f"Erro ao processar imagem {attachment.filename}: {e}")
        else:
            async with aiohttp.ClientSession() as session:
                for attachment in image_attachments:
                    try:
                        async with session.get(attachment.url) as resp:
                            if resp.status != 200:
                                logger.warning(f"Falha ao baixar imagem {attachment.filename}: status {resp.status}")
                                continue
                            image_data = await resp.read()

                        base64_img = base64.b64encode(image_data).decode("utf-8")
                        descricao, erro = await ollama.describe_image(base64_img, prompt_base)
                        if erro or not descricao:
                            logger.warning(f"Vision falhou em {attachment.filename}: {erro}")
                            continue

                        respostas.append(descricao.strip())
                    except Exception as e:
                        logger.error(f"Erro ao processar imagem {attachment.filename}: {e}")

        if not respostas:
            return None, "Não consegui analisar a imagem enviada."

        if len(respostas) == 1:
            return respostas[0], None
        return "\n\n".join(f"Imagem {i + 1}: {texto}" for i, texto in enumerate(respostas)), None

    async def _process_message(self, author, content: str, channel, attachments: list[discord.Attachment] | None = None) -> tuple:
        user_id = author.id
        user_name = author.display_name
        attachments = attachments or []

        roles_text = ""
        if isinstance(author, discord.Member):
            roles = [r.name for r in author.roles if r.name != '@everyone']
            if roles:
                roles.reverse()
                top_roles = roles[:3]
                roles_text = f" | Cargos no Servidor: {', '.join(top_roles)}"

        await db.get_or_create_user(user_id, user_name)

        vision_reply, vision_error = await self._run_vision_reply(content, attachments)
        if vision_reply:
            channel_id = channel.id
            await db.save_message(user_id, channel_id, "user", content or "[imagem enviada]")
            await db.save_message(user_id, channel_id, "assistant", vision_reply)
            return parse_emojis(vision_reply), None

        urls = extract_urls(content)
        url_context = ""
        if urls:
            for url in urls[:3]:
                fetched, err = await fetch_url_content(url)
                if fetched:
                    url_context += f"\n\n--- Conteúdo do link {url} ---\n{fetched}\n--- Fim do conteúdo ---\n"

        web_context = ""
        if len(content) > 5 and len(urls) == 0:
            import re
            content_lower = content.lower()

            keywords_tempo_real = [
                'hoje', 'agora', 'atual', 'atualmente', 'ontem',
                '2024', '2025', '2026', '2027',
                'novo', 'nova', 'novos', 'novas', 'lançou', 'lançamento', 'lançar',
                'último', 'última', 'recente', 'recentes',
                'preço', 'cotação', 'valor do', 'quanto custa', 'quanto tá',
                'notícia', 'notícias', 'aconteceu', 'acontecendo',
                'quem ganhou', 'quem venceu', 'resultado',
                'morreu', 'nasceu', 'casou',
                'album', 'álbum', 'música', 'filme', 'série', 'jogo',
                'eleição', 'presidente', 'governo',
                'copa', 'campeonato', 'mundial',
            ]
            keyword_hit = any(kw in content_lower for kw in keywords_tempo_real)

            ai_search_term = None
            if not keyword_hit:
                try:
                    prompt_decisao = (
                        "Responda APENAS 'SIM: termo de busca' ou 'NAO'. Nada mais.\n"
                        f"Pergunta: '{content}'\n"
                        "Essa pergunta exige dados da internet em tempo real para ser respondida corretamente?"
                    )
                    decisao, _ = await ollama.generate_simple(prompt_decisao)
                    logger.info(f"🧠 Decisão IA para pesquisa: '{decisao}'")
                    if decisao and "SIM:" in decisao.upper():
                        ai_search_term = decisao.split(":", 1)[1].strip().strip("'\"[]")
                        keyword_hit = True
                except Exception as e:
                    logger.warning(f"Decisão IA falhou (ignorando): {e}")

            if keyword_hit:
                if ai_search_term:
                    search_query = ai_search_term
                else:
                    search_query = re.sub(r'^(qual|quais|quem|quanto|como|onde|quando|o que|por que)\s+(é|são|foi|era|está|tá|fica|custa)\s*', '', content_lower).strip()
                    if len(search_query) < 5:
                        search_query = content

                logger.info(f"🕸️ Web Search disparado para: '{search_query}'")

                try:
                    resultados = await search_web(search_query, max_results=3)
                    if resultados:
                        web_context = (
                            f"\n\n[SISTEMA — PESQUISA WEB EM TEMPO REAL: Você pesquisou na internet sobre '{search_query}'. "
                            f"Use os resultados abaixo para complementar sua resposta. Cite as fontes quando relevante.\n\n"
                            f"{resultados}\n\n— Fim da Pesquisa Web.]\n"
                        )
                        logger.info(f"✅ Pesquisa retornou resultados para '{search_query}'")
                    else:
                        logger.warning(f"⚠️ Pesquisa não retornou resultados para '{search_query}'")
                except Exception as e:
                    logger.error(f"❌ Pesquisa falhou e foi pulada: {e}")

        ticket_intent = None
        if self._is_ticket_channel(channel) and content.strip():
            ticket_intent = await self._classify_ticket_intent(content, channel)
            if ticket_intent:
                logger.info(
                    "Ticket %s classificado como intent=%s confidence=%s next_step=%s",
                    channel.id,
                    ticket_intent["intent"],
                    ticket_intent["confidence"],
                    ticket_intent["next_step"],
                )

        approved_knowledge_entries = []
        guild = getattr(channel, "guild", None)
        if guild and content.strip():
            approved_knowledge_entries = await get_relevant_admin_knowledge(
                guild.id,
                content,
                is_ticket=self._is_ticket_channel(channel),
                limit=4,
            )
            if approved_knowledge_entries:
                logger.info(
                    "Conhecimento aprovado usado no canal %s: entradas=%s",
                    channel.id,
                    ", ".join(str(entry["id"]) for entry in approved_knowledge_entries),
                )

        final_content = content or "[imagem enviada]"
        if url_context:
            final_content += f"\n\n[O usuário compartilhou links. Aqui está o conteúdo extraído para sua análise:]{url_context}"
            
        if web_context:
            final_content += web_context

        context_info = self._build_context(user_name, channel, roles_text, content)
        enriched_content = final_content + context_info
        approved_knowledge_context = format_admin_knowledge_context(approved_knowledge_entries)
        if approved_knowledge_context:
            enriched_content += "\n\n" + approved_knowledge_context
        ticket_intent_context = self._build_ticket_intent_context(ticket_intent)
        if ticket_intent_context:
            enriched_content += "\n\n" + ticket_intent_context

        channel_id = channel.id
        await db.save_message(user_id, channel_id, "user", final_content)

        history = await self._get_history(user_id, channel_id)

        if history and history[-1]['role'] == 'user':
            history[-1]['content'] = enriched_content

        persona = user_personas[user_id]
        resposta, erro = await ollama.chat(history, persona=persona)

        if resposta:
            resposta = parse_emojis(resposta)

            chamar_staff = False
            if "[CHAMAR_STAFF]" in resposta:
                resposta = resposta.replace("[CHAMAR_STAFF]", "").strip()
                chamar_staff = True
            elif ticket_intent and ticket_intent["next_step"] == "chamar_staff" and self._is_ticket_channel(channel):
                chamar_staff = True
                if "equipe" not in resposta.lower() and "staff" not in resposta.lower():
                    resposta += "\n\nVou encaminhar isso para a equipe concluir seu atendimento."

            await db.save_message(user_id, channel_id, "assistant", resposta)

            is_ticket_channel = self._is_ticket_channel(channel)

            if chamar_staff and is_ticket_channel:
                await db.ignore_channel(channel_id)
                resposta += f"\n\n<@&{STAFF_ROLE_ID}> — **Uma pessoa da equipe assumirá este atendimento em breve! (A IA foi pausada).**"
                logger.info(f"🚨 A IA decidiu transferir o canal #{channel.name} para um humano.")
            elif chamar_staff:
                logger.warning(f"⚠️ A IA tentou usar [CHAMAR_STAFF] fora de um ticket (canal: {getattr(channel, 'name', 'Desconhecido')}). Ação ignorada.")

            try:
                log_channel_id = await db.get_bot_config("log_channel")
                if log_channel_id:
                    log_channel = self.bot.get_channel(int(log_channel_id))
                    if log_channel:
                        is_dm = isinstance(channel, discord.DMChannel)
                        origem = "🔏 Mensagem Direta (DM)" if is_dm else f"💬 <#{channel.id}> no servidor: {channel.guild.name}"
                        
                        import textwrap
                        short_content = textwrap.shorten(content, width=1000, placeholder="...")
                        short_resposta = textwrap.shorten(resposta, width=1000, placeholder="...")
                        
                        text_log = (
                            f"**{emoji('wShield', '🕵️')} Monitoramento de Conversa**\n\n"
                            f"**Origem:** {origem}\n"
                            f"**Usuário:** <@{user_id}> ({user_name})\n\n"
                            f"**Mortal:**\n```\n{short_content}\n```\n\n"
                            f"**IA:**\n```\n{short_resposta}\n```"
                        )
                        await send_components(self.bot, log_channel.id, [container([section(text_log)])])
                        
            except Exception as e:
                logger.error(f"Erro no monitoramento de chat: {e}")

            try:
                is_dm = isinstance(channel, discord.DMChannel)
                origem_local = "DM" if is_dm else f"#{channel.name} ({channel.guild.name})"
                
                with open("ai_chat.log", "a", encoding="utf-8") as f:
                    f.write(f"[{now_br().strftime('%d/%m/%Y %H:%M:%S')}] Usuário: {user_name} ({user_id}) | Local: {origem_local}\n")
                    f.write(f"Usuário diz: {content}\n")
                    f.write(f"Oris responde: {resposta}\n")
                    f.write("-" * 80 + "\n")
            except Exception as e:
                logger.error(f"Erro ao escrever no arquivo ai_chat.log: {e}")

        if vision_error and not resposta and not erro:
            return None, vision_error

        return resposta, erro

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.content.startswith('!'):
            return

        if message.guild:
            is_admin = getattr(message.author, 'guild_permissions', None) and message.author.guild_permissions.administrator
            is_owner = message.author.id == OWNER_ID
            
            if not is_admin and not is_owner:
                bot_channel_id = await db.get_bot_channel(message.guild.id)
                is_ticket = self._is_ticket_routing_channel(message.channel)
                if bot_channel_id and message.channel.id != bot_channel_id and not is_ticket:
                    return

        is_dm = isinstance(message.channel, discord.DMChannel)

        is_mentioned = False
        if not is_dm:
            bot_mentioned = self.bot.user in message.mentions
            bot_replied = message.reference and getattr(message.reference.resolved, "author", None) == self.bot.user
            role_mentioned = any(r in message.role_mentions for r in message.guild.me.roles)
            
            is_ticket_channel = self._is_ticket_routing_channel(message.channel)
            
            is_mentioned = bot_mentioned or bot_replied or role_mentioned or is_ticket_channel

        if not is_dm and not is_mentioned:
            return

        if not is_dm and self._is_ticket_routing_channel(message.channel):
            if await db.is_channel_ignored(message.channel.id):
                return

            if is_staff_member(message.author):
                await db.ignore_channel(message.channel.id)
                logger.info(f"👨‍💻 Staff assumiu o ticket #{message.channel.name}. Desligando a IA.")
                await send_msg(self.bot, message.channel.id, "IA Desativada", "Equipe Humana conectada. A partir de agora um staff conduzirá sua solicitação isoladamente.", ping=message.author.mention)
                return

            keywords = ["falar com humano", "chamar suporte", "chamar um humano", "atendente", "alguém da equipe", "chamar staff", "não quero falar com bot", "falar com pessoa"]
            if any(kw in message.content.lower() for kw in keywords):
                await db.ignore_channel(message.channel.id)
                logger.info(f"🚨 Chamado para Humano no ticket #{message.channel.name}.")
                msg = "Passei o seu chamado para a nossa equipe humana. Assim que possível, um Staff assumirá este ticket para te atender pessoalmente!\n\n*(A inteligência artificial foi pausada temporariamente neste canal).*"
                await send_msg(self.bot, message.channel.id, "Transferindo Atendimento...", msg, icon="wAlert", fallback="⚠️", ping=f"<@&{STAFF_ROLE_ID}>")
                return

        content = message.content
        if not is_dm:
            content = content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()
            for r in message.guild.me.roles:
                content = content.replace(f'<@&{r.id}>', '').strip()

        has_image_attachments = any(
            attachment.content_type and attachment.content_type.startswith("image/")
            for attachment in message.attachments
        )

        if not content and not has_image_attachments:
            return

        bucket = self.chat_cooldown.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            logger.warning(f"Spam bloqueado do user {message.author.name}. Restam {retry_after:.1f}s.")
            walert = emoji("wAlert", "⚠️")
            comps = [container([section(f"**{walert} Devagar Campeão!**\n\nPor favor, aguarde `{retry_after:.1f}s` antes de conversar comigo novamente.")])]
            # Envia menção e apaga rápido visualmente via HTTP puro ou mensagem crua.
            m = await message.reply(f"**{walert} Devagar Campeão!** Aguarde `{retry_after:.1f}s`.")
            await m.delete(delay=4.0)
            return

        async with message.channel.typing():
            resposta, erro = await self._process_message(
                message.author,
                content,
                message.channel,
                message.attachments
            )

            if erro:
                await send_msg(self.bot, message.channel.id, "Erro no Processamento", erro, True, ping=message.author.mention)
            else:
                parts = split_message(resposta)
                for i, part in enumerate(parts):
                    if i == 0:
                        await message.reply(part)
                    else:
                        await message.channel.send(part)

    @commands.command(name='chat')
    async def cmd_chat(self, ctx: commands.Context, *, mensagem: str):
        """💬 Conversa com a IA. Uso: !chat <sua mensagem>"""
        async with ctx.channel.typing():
            resposta, erro = await self._process_message(
                ctx.author,
                mensagem,
                ctx.channel
            )

            if erro:
                await send_msg(self.bot, ctx.channel.id, "Erro", erro, True)
            else:
                parts = split_message(resposta)
                for part in parts:
                    await ctx.send(part)

    @commands.command(name='dm')
    async def cmd_dm(self, ctx: commands.Context):
        """📩 Inicia conversa privada com o bot."""
        try:
            dm_channel = await ctx.author.create_dm()
            saudacao = get_greeting()
            text = (
                f"**{emoji('wCheck', '📩')} Chat Privado Iniciado!**\n\n"
                f"{saudacao}, **{ctx.author.display_name}**!\n\n"
                f"No privado você pode:\n"
                f"• Conversar diretamente (sem precisar me mencionar)\n"
                f"• Usar todos os comandos normalmente\n"
                f"• Compartilhar links para eu analisar\n"
                f"• Ter conversas confidenciais isoladas do servidor"
            )
            await send_components(self.bot, dm_channel.id, [container([section(text)])])
            await ctx.send(f"📩 {ctx.author.mention}, te mandei uma mensagem privada! Verifique suas DMs.")
        except discord.Forbidden:
            await ctx.send(f"❌ {ctx.author.mention}, não consegui te enviar DM. Habilite em Configurações > Privacidade.")

    @commands.command(name='reset')
    async def cmd_reset(self, ctx: commands.Context):
        """🔄 Limpa seu histórico de conversa neste canal."""
        await db.clear_conversation(ctx.author.id, ctx.channel.id)
        user_personas[ctx.author.id] = "padrao"
        await db.set_user_persona(ctx.author.id, "padrao")
        await send_msg(self.bot, ctx.channel.id, "Histórico Limpo!", "🧹 Seu histórico de conversa e persona predefinida foram volatilizados da nuvem temporária. Podemos recomeçar limpos!")

    @commands.command(name='persona')
    async def cmd_persona(self, ctx: commands.Context, tipo: str = None):
        """🎭 Muda a personalidade da IA. Uso: !persona <tipo>"""
        if tipo is None or tipo.lower() not in PERSONAS:
            tipos = ', '.join(f'`{p}`' for p in PERSONAS.keys())
            current = user_personas[ctx.author.id]
            msg = f"Injete o comando `!persona <tipo>` com uma das classes abaixo:\n\n{tipos}\n\n**Protocolo Injetado Atualmente:** `{current}`"
            await send_msg(self.bot, ctx.channel.id, "Personas da Interface", msg, icon="wPy", fallback="🎭")
            return

        user_personas[ctx.author.id] = tipo.lower()
        await db.set_user_persona(ctx.author.id, tipo.lower())

        nomes = {
            "padrao": "🤖 Padrão",
            "programador": "💻 Programador Expert",
            "professor": "📚 Professor Didático",
            "humorista": "😂 Humorista",
            "formal": "👔 Formal Corporativo",
            "criativo": "🎨 Criativo",
        }
        await send_msg(self.bot, ctx.channel.id, "Sistema Reinjetado", f"Minha lógica comportamental foi substituída: **{nomes.get(tipo.lower(), tipo)}**")

    @commands.command(name='resumo')
    async def cmd_resumo(self, ctx: commands.Context):
        """📋 Resume a conversa até agora."""
        history = await self._get_history(ctx.author.id, ctx.channel.id)
        if len(history) < 2:
            await send_msg(self.bot, ctx.channel.id, "Memória Insuficiente", "Sem acúmulo de tráfego. Ainda não temos contexto suficiente no seu nome e neste canal.", icon="wCloud", fallback="☁️")
            return

        async with ctx.channel.typing():
            prompt = "Resuma de forma concisa toda a nossa conversa até agora. Liste os pontos principais discutidos."
            history_copy = history.copy()
            history_copy.append({"role": "user", "content": prompt})

            resposta, erro = await ollama.chat(history_copy)
            if erro:
                await send_msg(self.bot, ctx.channel.id, "Erro no LLM Principal", erro, True)
            else:
                text = f"**{emoji('wList', '📋')} Resumo Extraído da Memória Voláti**\n\n{parse_emojis(resposta[:4096])}"
                rodape = f"-# Memória varrida das últimas {len(history)} interações salvadas sob <@{ctx.author.id}>."
                await send_components(self.bot, ctx.channel.id, [container([section(text), text_display(rodape)])])

    @commands.command(name='criativo')
    async def cmd_criativo(self, ctx: commands.Context, *, prompt: str):
        """🎨 Modo criativo — histórias, poemas, ideias. Uso: !criativo <prompt>"""
        async with ctx.channel.typing():
            messages = [{"role": "user", "content": prompt}]
            resposta, erro = await ollama.chat(messages, persona="criativo")

            if erro:
                await send_msg(self.bot, ctx.channel.id, "Falha na Criação Visual", erro, True)
            else:
                parts = split_message(parse_emojis(resposta))
                for i, part in enumerate(parts):
                    header = f"**{emoji('wPy', '🎨')} Processo Criativo**\n\n" if i == 0 else ""
                    await send_components(self.bot, ctx.channel.id, [container([section(f"{header}{part}")])])

    @commands.command(name='debater')
    async def cmd_debater(self, ctx: commands.Context, *, tema: str):
        """⚖️ Debate um tema com prós e contras. Uso: !debater <tema>"""
        async with ctx.channel.typing():
            prompt = (
                f"Faça um debate sobre o tema: '{tema}'\n\n"
                "Apresente:\n"
                "**🟢 ARGUMENTOS A FAVOR:**\n(3 argumentos fortes)\n\n"
                "**🔴 ARGUMENTOS CONTRA:**\n(3 argumentos fortes)\n\n"
                "**⚖️ CONCLUSÃO EQUILIBRADA:**\n(sua análise imparcial)"
            )
            messages = [{"role": "user", "content": prompt}]
            resposta, erro = await ollama.chat(messages)

            if erro:
                await send_msg(self.bot, ctx.channel.id, "Debate Interrompido", erro, True)
            else:
                parts = split_message(parse_emojis(resposta))
                for i, part in enumerate(parts):
                    header = f"**{emoji('wPy', '⚖️')} Juízo Simulado**\n\n" if i == 0 else ""
                    await send_components(self.bot, ctx.channel.id, [container([section(f"{header}{part}")])])

    @commands.command(name='link')
    async def cmd_link(self, ctx: commands.Context, *, url: str):
        """🔗 Lê e analisa o conteúdo de um link. Uso: !link <url>"""
        async with ctx.channel.typing():
            loading = await ctx.send(f"**{emoji('wSearch', '🔍')} Crawlando o payload do link...**")

            conteudo, erro = await fetch_url_content(url)
            if erro:
                await send_msg(self.bot, ctx.channel.id, "Nó DNS falhou", erro, True)
                await loading.delete()
                return

            prompt = (
                f"O usuário pediu para analisar o seguinte link: {url}\n\n"
                f"Conteúdo extraído:\n{conteudo}\n\n"
                "Por favor:\n"
                "1. Resuma o conteúdo principal\n"
                "2. Identifique os pontos mais importantes\n"
                "3. Dê sua análise/opinião sobre o conteúdo"
            )
            messages = [{"role": "user", "content": prompt}]
            resposta, erro_ia = await ollama.chat(messages)

            await loading.delete()
            if erro_ia:
                await send_msg(self.bot, ctx.channel.id, "Oris Engine Err", erro_ia, True)
            else:
                text = f"**{emoji('wPy', '🔍')} Análise de Website Injetada**\n\n{parse_emojis(resposta[:4096])}"
                rodape = f"-# O conteúdo foi acessado de forma direta a partir do servidor em background (não via navegador)"
                await send_components(self.bot, ctx.channel.id, [container([section(text), text_display(rodape)])])


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
