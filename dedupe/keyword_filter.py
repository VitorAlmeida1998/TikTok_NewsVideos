"""Filtro de relevância por palavras-chave.

O dedupe por hash (título+URL) já acontece em shared/db.save_item.
Este módulo cuida da segunda etapa: decidir se um item já salvo é
relevante o suficiente para virar roteiro/vídeo, com base em palavras-chave
que indicam "notícia quente" (leak, reveal, delay, launch, exclusive, etc.).
"""
from __future__ import annotations

import re

# Palavras-chave (case-insensitive) que indicam notícia de alto interesse.
# Mantido em inglês pois os feeds fonte são internacionais.
DEFAULT_KEYWORDS: list[str] = [
    "leak",
    "leaked",
    "leaks",
    "reveal",
    "revealed",
    "reveals",
    "delay",
    "delayed",
    "launch",
    "launches",
    "launched",
    "exclusive",
    "announce",
    "announced",
    "announces",
    "release date",
    "trailer",
    "confirmed",
    "confirms",
]


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
