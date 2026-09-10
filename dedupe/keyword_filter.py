"""Filtro e pontuação de relevância por palavras-chave.

O dedupe por hash (título+URL) já acontece em shared/db.save_item.
Este módulo cuida da segunda etapa: decidir se um item já salvo é
relevante o suficiente para virar roteiro/vídeo, com base em palavras-chave
que indicam "notícia quente" (leak, reveal, delay, launch, exclusive, etc.),
e dar uma pontuação pra ordenar o que vira vídeo primeiro quando o pipeline
roda sozinho com limite por rodada.
"""
from __future__ import annotations

import re

# Peso de cada palavra-chave: quanto mais "furo"/impacto pro público de
# TikTok, maior. Só as chaves deste dict contam como relevância.
KEYWORD_WEIGHTS: dict[str, float] = {
    "leak": 5,
    "leaked": 5,
    "leaks": 5,
    "exclusive": 4,
    "release date": 4,
    "delay": 4,
    "delayed": 4,
    "confirmed": 3,
    "confirms": 3,
    "reveal": 3,
    "revealed": 3,
    "reveals": 3,
    "announce": 3,
    "announced": 3,
    "announces": 3,
    "launch": 2,
    "launches": 2,
    "launched": 2,
    "trailer": 2,
    # gatilhos de compartilhamento ("manda pro amigo"): afetam decisão de
    # compra/tempo de alguém ou são drama — são o que mais viaja por DM
    "free": 3,
    "price": 3,
    "cancelled": 4,
    "canceled": 4,
    "shut down": 3,
    "shuts down": 3,
    "remake": 3,
    "remaster": 2,
    "spoiler": 3,
    "spoilers": 3,
    "banned": 3,
    "lawsuit": 2,
    "record": 2,
}

DEFAULT_KEYWORDS: list[str] = list(KEYWORD_WEIGHTS)

# Franquias/plataformas que puxam muita atenção no TikTok BR — bônus por
# menção no título ou resumo (uma vez cada).
HYPE_TERMS: dict[str, float] = {
    "gta": 4,
    "grand theft auto": 4,
    "nintendo": 2,
    "switch 2": 3,
    "playstation": 2,
    "ps5": 2,
    "ps6": 3,
    "xbox": 2,
    "zelda": 3,
    "mario": 2,
    "pokemon": 3,
    "pokémon": 3,
    "call of duty": 3,
    "elden ring": 3,
    "fortnite": 2,
    "minecraft": 2,
    "resident evil": 3,
    "god of war": 3,
    "the witcher": 3,
    "half-life": 4,
    "hollow knight": 2,
    "silksong": 3,
    "steam": 1,
}

# Peso por fonte (as fontes em si ficam em feeds.yaml). Critério: quem dá a
# notícia primeiro e quem fala com o público que assiste TikTok pesa mais;
# pauta de indústria/negócios pesa menos. Fonte não listada vale 1.0.
SOURCE_WEIGHTS: dict[str, float] = {
    # oficiais: é o anúncio em si, não a repercussão dele
    "playstation": 1.4,
    "xbox": 1.3,
    # furo/vazamento: costuma ser a origem da história
    "vgc": 1.3,
    "insidergaming": 1.25,
    # imprensa generalista
    "ign": 1.2,
    "eurogamer": 1.1,
    "gamespot": 1.1,
    "polygon": 1.0,
    "pcgamer": 1.0,
    "kotaku": 1.0,
    # plataformas que puxam muito no público BR
    "nintendolife": 1.15,
    "pushsquare": 1.1,
    # B2B/indústria: interessa pouco a quem rola o feed
    "gamesindustry": 0.7,
}

TITLE_MULTIPLIER = 1.5  # keyword no título vale mais que só no resumo

# Decaimento por frescor: notícia de games perde valor rápido — quando o
# assunto já está em todo lugar, o vídeo não tem mais vantagem nenhuma. O
# multiplicador cai de 1.0 (agora) até FRESHNESS_FLOOR em FRESHNESS_HOURS.
FRESHNESS_HOURS = 72.0
FRESHNESS_FLOOR = 0.15


def freshness_multiplier(age_hours: float) -> float:
    """Peso por idade da notícia: 1.0 recém-saída, caindo até FRESHNESS_FLOOR."""
    decay = 1.0 - max(0.0, age_hours) / FRESHNESS_HOURS
    return max(FRESHNESS_FLOOR, decay)


def _build_pattern(keywords: list[str]) -> re.Pattern:
    # \b...\b para não casar substrings dentro de outras palavras;
    # keywords com espaço (ex: "release date") funcionam normalmente.
    escaped = [re.escape(k) for k in keywords]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def find_matched_keywords(
    title: str, summary: str = "", keywords: list[str] | None = None
) -> list[str]:
    """Retorna a lista de palavras-chave (da lista `keywords`) encontradas
    no título ou resumo do item, preservando a ordem da lista de keywords
    e sem duplicatas.
    """
    keywords = keywords if keywords is not None else DEFAULT_KEYWORDS
    pattern = _build_pattern(keywords)
    text = f"{title} {summary}"

    found_lower = {m.group(0).lower() for m in pattern.finditer(text)}

    matched: list[str] = []
    for kw in keywords:
        if kw.lower() in found_lower and kw not in matched:
            matched.append(kw)
    return matched


def is_relevant(
    title: str, summary: str = "", keywords: list[str] | None = None
) -> bool:
    """True se o item contém ao menos uma palavra-chave de relevância."""
    return len(find_matched_keywords(title, summary, keywords)) > 0


def relevance_score(
    title: str, summary: str = "", source: str = "", matched: list[str] | None = None
) -> float:
    """Pontuação de relevância (maior = vira vídeo antes).

    soma dos pesos das keywords (x1.5 se no título) + bônus de hype
    (franquias/plataformas), tudo multiplicado pelo peso da fonte.
    """
    matched = matched if matched is not None else find_matched_keywords(title, summary)
    if not matched:
        return 0.0

    title_lower = title.lower()
    text_lower = f"{title} {summary}".lower()

    score = 0.0
    for kw in matched:
        weight = KEYWORD_WEIGHTS.get(kw.lower(), 1.0)
        in_title = re.search(r"\b" + re.escape(kw.lower()) + r"\b", title_lower) is not None
        score += weight * (TITLE_MULTIPLIER if in_title else 1.0)

    for term, bonus in HYPE_TERMS.items():
        if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
            score += bonus

    return round(score * SOURCE_WEIGHTS.get(source.lower(), 1.0), 2)
