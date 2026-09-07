"""Parsing e normalização de feeds RSS/Atom em NewsItem.

Separado em duas camadas:
- fetch_feed(url): faz a chamada de rede (não testado com fixtures locais)
- parse_feed(raw_content, source_name): parseia texto/bytes já obtidos,
  permitindo testes 100% offline com fixtures locais.
"""
from __future__ import annotations

from datetime import datetime, timezone
from time import struct_time

import feedparser

from shared.models import NewsItem


def fetch_feed(url: str) -> str | bytes:
    """Busca o conteúdo bruto de um feed RSS/Atom via HTTP."""
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Falha ao buscar/parsear feed em {url}: {parsed.bozo_exception}")
    return url


def _struct_time_to_datetime(t: struct_time | None) -> datetime | None:
    if t is None:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc)


def parse_feed(raw_content: str | bytes, source_name: str) -> list[NewsItem]:
    """Parseia o conteúdo bruto (string/bytes) de um feed em uma lista de NewsItem.

    `raw_content` pode ser o próprio texto XML do feed (usado em testes)
    ou uma URL (feedparser aceita ambos).
    """
    parsed = feedparser.parse(raw_content)

    items: list[NewsItem] = []
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue

        summary = entry.get("summary", "") or entry.get("description", "")
        published = _struct_time_to_datetime(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )

        items.append(
            NewsItem(
                title=title,
                source=source_name,
                url=url,
                published_at=published,
                summary=summary.strip(),
            )
        )

    return items
