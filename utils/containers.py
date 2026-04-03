"""
Discord Components V2 — Containers Tier 17
Constrói e envia mensagens com o visual premium de containers do Discord.
Usa a API raw para enviar payloads que o discord.py ainda não suporta nativamente.
"""

import os
import json
from copy import deepcopy
from discord.http import Route


def _load_emojis() -> dict:
    """Carrega o mapa de emojis customizados."""
    try:
        path = os.path.join("data", "emojis.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}


def e(name: str, fallback: str = "") -> str:
    """Retorna string formatada do emoji customizado ou fallback unicode."""
    emojis = _load_emojis()
    return emojis.get(name, fallback)


def emoji_obj(name: str):
    """Retorna dict {name, id} para uso em campos de emoji de select options."""
    emojis = _load_emojis()
    raw = emojis.get(name)
    if raw and raw.startswith("<:"):
        parts = raw.strip("<>").split(":")
        if len(parts) == 3:
            return {"name": parts[1], "id": parts[2]}
    return None


def parse_emojis(text: str) -> str:
    """Substitui :emoji_name: no texto pelas tags '<:emoji_name:id>' do Discord."""
    import re
    if not text:
        return text
    
    emojis = _load_emojis()
    if not emojis:
        return text

    def replacer(match):
        name = match.group(1)
        if name in emojis:
            return emojis[name]
        return match.group(0)

    # 1. Corrige tags nativas do Discord caso a IA tenha memorizado ou alucinado um ID numérico antigo/falso
    text = re.sub(r'<:([a-zA-Z0-9_]+):\d+>', replacer, text)
    # 2. Busca padrões em texto puro como :wCloud: ou :wArrow:, ignorando os já corrigidos
    return re.sub(r'(?<!<):([a-zA-Z0-9_]+):', replacer, text)


# ========================================
# BUILDERS — Montam os componentes V2
# ========================================

def container(components: list, accent_color: int = 0) -> dict:
    """Container visual (type 17). Aceita sections, text_displays, separators, action_rows."""
    return {"type": 17, "accent_color": accent_color, "components": components}


def section(text: str, thumbnail_url: str = None) -> dict:
    """Section (type 9) com texto e thumbnail lateral opcional (faz fallback pra block puro)."""
    if thumbnail_url:
        return {
            "type": 9,
            "components": [{"type": 10, "content": text}],
            "accessory": {"type": 11, "media": {"url": thumbnail_url}}
        }
    return {"type": 10, "content": text}


def text_display(content: str) -> dict:
    """Bloco de texto puro (type 10)."""
    return {"type": 10, "content": content}


def separator(divider: bool = True, spacing: int = 1) -> dict:
    """Separador visual (type 14)."""
    return {"type": 14, "divider": divider, "spacing": spacing}


def action_row(*components) -> dict:
    """Action Row (type 1) — container de botões/selects."""
    return {"type": 1, "components": list(components)}


def string_select(custom_id: str, placeholder: str, options: list) -> dict:
    """String Select Menu (type 3)."""
    return {
        "type": 3,
        "custom_id": custom_id,
        "placeholder": placeholder,
        "min_values": 1,
        "max_values": 1,
        "options": options
    }


def select_option(label: str, value: str, description: str = None, emoji_name: str = None) -> dict:
    """Opção individual para um select com emoji customizado."""
    opt = {"label": label[:100], "value": value[:100]}
    if description:
        opt["description"] = description[:100]
    if emoji_name:
        emo = emoji_obj(emoji_name)
        if emo:
            opt["emoji"] = emo
    return opt


# ========================================
# SENDERS — Enviam via API raw do Discord
# ========================================

async def send_components(bot, channel_id: int, components: list, content: str = None):
    """Envia mensagem Components V2 em um canal via API raw."""
    payload = {"flags": 1 << 15, "components": _merge_content_into_components(components, content)}
    route = Route('POST', '/channels/{channel_id}/messages', channel_id=channel_id)
    return await bot.http.request(route, json=payload)


async def edit_interaction(bot, interaction_token: str, components: list):
    """Edita resposta original de uma interação com containers V2."""
    payload = {"flags": 1 << 15, "components": components}
    route = Route(
        'PATCH',
        '/webhooks/{application_id}/{interaction_token}/messages/@original',
        application_id=bot.application_id,
        interaction_token=interaction_token
    )
    return await bot.http.request(route, json=payload)


def _merge_content_into_components(components: list, content: str = None) -> list:
    """
    Components V2 nao aceita payload.content.
    Quando houver mencao/ping, injeta esse texto no primeiro bloco textual.
    """
    if not content:
        return components

    merged = deepcopy(components)
    prefix = content.strip()

    for component in merged:
        if _inject_into_component(component, prefix):
            return merged

    merged.insert(0, {"type": 10, "content": prefix})
    return merged


def _inject_into_component(component: dict, prefix: str) -> bool:
    """Insere texto no primeiro componente textual encontrado."""
    if not isinstance(component, dict):
        return False

    comp_type = component.get("type")

    if comp_type == 10:
        original = component.get("content", "")
        component["content"] = f"{prefix}\n{original}".strip()
        return True

    if comp_type == 9:
        nested = component.get("components", [])
        for child in nested:
            if _inject_into_component(child, prefix):
                return True
        nested.insert(0, {"type": 10, "content": prefix})
        component["components"] = nested
        return True

    for child in component.get("components", []):
        if _inject_into_component(child, prefix):
            return True

    return False
