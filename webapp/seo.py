"""Checklist de SEO/descoberta para o roteiro de um item.

As regras vêm da análise dos primeiros 19 vídeos (ver ROADMAP.md): o que
falhava era legenda ausente, hashtag só em inglês (o público é BR e busca em
português), hashtag quebrada com espaço, hook longo demais e abertura sempre
igual ("GENTE,") — coisas que o painel consegue apontar antes de publicar.

Funções puras sobre os campos do roteiro; quem monta a lista (app.py) só
passa o item e os hooks recentes.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Hashtags que o público brasileiro realmente digita na busca do TikTok.
# Basta UMA delas aparecer (como palavra inteira dentro da hashtag).
BR_HASHTAG_TERMS = [
    "games",
    "jogos",
    "jogo",
    "noticiasdegames",
    "gamesbr",
    "vazou",
    "novidades",
    "gamenews",
    "noticias",
]

MAX_LEAD_CHARS = 150
MIN_HASHTAGS = 4
MAX_HASHTAGS = 6
MAX_HOOK_WORDS = 12


@dataclass
class SeoCheck:
    ok: bool
    label: str
    hint: str = ""


def _field(item: Any, key: str) -> str:
    """Lê um campo tanto de dict quanto de sqlite3.Row (que não tem .get)."""
    try:
        value = item[key]
    except (KeyError, IndexError, TypeError):
        return ""
    return (value or "").strip() if isinstance(value, str) else ""


def extract_hashtags(description: str) -> list[str]:
    """Hashtags da legenda, sem o '#' e em minúsculo."""
    return [tag.lower() for tag in re.findall(r"#([^\s#]+)", description or "")]


def caption_lead(description: str) -> str:
    """Texto da legenda antes da primeira hashtag — é o que o TikTok mostra
    no feed antes do "ver mais" e o que ele indexa como texto de busca."""
    if not description:
        return ""
    return description.split("#", 1)[0].strip()


def hashtags_with_space(description: str) -> list[str]:
    """Detecta hashtag "quebrada" por espaço (ex: "#leon kennedy", que o
    TikTok registra só como #leon).

    Heurística: no bloco final de hashtags, qualquer palavra que não comece
    com '#' é continuação indevida da hashtag anterior.
    """
    if not description or "#" not in description:
        return []
    tail = description[description.index("#") :]
    broken = []
    current = None
    for token in tail.split():
        if token.startswith("#"):
            current = token
        elif current:
            broken.append(f"{current} {token}")
            current = None
    return broken


def hashtags_with_accent(description: str) -> list[str]:
    """Hashtags com acento/cedilha — viram outra hashtag (ou nenhuma) na busca."""
    accented = []
    for tag in extract_hashtags(description):
        if any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", tag)):
            accented.append(tag)
    return accented


def has_br_hashtag(description: str) -> bool:
    tags = extract_hashtags(description)
    return any(term in tag for tag in tags for term in BR_HASHTAG_TERMS)


def first_word(text: str) -> str:
    """Primeira palavra normalizada (minúscula, sem pontuação) — usada pra
    detectar aberturas repetidas."""
    words = re.findall(r"[^\W_]+", (text or "").lower(), flags=re.UNICODE)
    return words[0] if words else ""


def check_seo(item: Any, recent_hooks: list[str] | None = None) -> list[SeoCheck]:
    """Checklist completo para um item. `recent_hooks` deve vir SEM o hook do
    próprio item (senão ele sempre acusa repetição consigo mesmo)."""
    description = _field(item, "script_description")
    hook = _field(item, "script_hook")
    cta = _field(item, "script_cta")
    game_name = _field(item, "game_name")
    recent_hooks = recent_hooks or []

    checks: list[SeoCheck] = []

    checks.append(
        SeoCheck(
            bool(description),
            "Legenda preenchida",
            "Sem legenda o TikTok não tem texto pra indexar — o vídeo só aparece pra quem cai nele.",
        )
    )

    lead = caption_lead(description)
    checks.append(
        SeoCheck(
            bool(lead) and len(lead) <= MAX_LEAD_CHARS,
            f"Primeira frase ≤ {MAX_LEAD_CHARS} caracteres ({len(lead)})",
            "O feed corta a legenda: o jogo e o assunto têm que caber antes do 'ver mais'.",
        )
    )

    tags = extract_hashtags(description)
    checks.append(
        SeoCheck(
            MIN_HASHTAGS <= len(tags) <= MAX_HASHTAGS,
            f"{MIN_HASHTAGS} a {MAX_HASHTAGS} hashtags ({len(tags)})",
            "Poucas hashtags limitam a descoberta; muitas hashtag genérica o TikTok lê como spam.",
        )
    )

    checks.append(
        SeoCheck(
            has_br_hashtag(description),
            "Tem hashtag em português",
            "O público é BR e busca em português (#games, #jogos, #noticiasdegames, #vazou).",
        )
    )

    broken = hashtags_with_space(description)
    checks.append(
        SeoCheck(
            not broken,
            "Nenhuma hashtag com espaço",
            "Hashtag com espaço vira outra: " + ", ".join(broken) if broken else "",
        )
    )

    accented = hashtags_with_accent(description)
    checks.append(
        SeoCheck(
            not accented,
            "Nenhuma hashtag com acento",
            "Hashtag com acento não casa com a que o público digita: "
            + ", ".join(f"#{t}" for t in accented)
            if accented
            else "",
        )
    )

    checks.append(
        SeoCheck(
            bool(game_name),
            "Nome do jogo preenchido",
            "Sem o nome do jogo não há busca de fundo/música nem hashtag específica.",
        )
    )

    hook_words = len(hook.split())
    checks.append(
        SeoCheck(
            bool(hook) and hook_words <= MAX_HOOK_WORDS,
            f"Hook com até {MAX_HOOK_WORDS} palavras ({hook_words})",
            "Hook longo perde a pessoa antes de terminar de ser falado.",
        )
    )

    opening = first_word(hook)
    repeated = [h for h in recent_hooks if opening and first_word(h) == opening]
    checks.append(
        SeoCheck(
            not repeated,
            "Abertura diferente dos últimos vídeos",
            f"'{opening.upper()}' já abriu {len(repeated)} dos últimos roteiros — repetir vira tique."
            if repeated
            else "",
        )
    )

    checks.append(
        SeoCheck(
            bool(cta),
            "CTA preenchido",
            "Sem chamada final o vídeo não puxa comentário, seguidor nem envio pra amigo.",
        )
    )

    return checks


def seo_score(checks: list[SeoCheck]) -> tuple[int, int]:
    """(quantos passaram, total) — para o resumo no topo do checklist."""
    return sum(1 for c in checks if c.ok), len(checks)
