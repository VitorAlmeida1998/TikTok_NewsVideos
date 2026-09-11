"""Parsing e normalização de feeds RSS/Atom em NewsItem.

Separado em duas camadas:
- fetch_feed(url, ...): faz a chamada de rede (não testado com fixtures locais)
- parse_feed(raw_content, source_name): parseia texto/bytes já obtidos,
  permitindo testes 100% offline com fixtures locais.

A busca usa GET condicional (ETag/Last-Modified): o monitor checa os feeds a
cada 2 minutos e, sem isso, baixaria todos os portais inteiros ~30x por hora
cada. Com os cabeçalhos, o servidor responde 304 (sem corpo) quando nada
mudou — mais rápido pra nós e educado com quem hospeda o feed.

O HTTP é feito com `requests`, não pela camada interna do feedparser, por
dois motivos concretos: ela não aceita timeout (um feed lento travaria o
ciclo inteiro do monitor) e, em alguns feeds (nintendolife, pushsquare),
falha com "undefined entity" num conteúdo que o feedparser lê sem problema
quando recebe os bytes já baixados.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import struct_time

import feedparser
import requests

from shared.models import NewsItem

# Identifica o cliente (pra quem hospeda o feed saber quem está buscando) no
# formato convencional de leitor de RSS. A palavra "bot" no User-Agent faz
# vários portais responderem 403 no WAF — testado: xbox, vgc, gamespot,
# nintendolife e pushsquare bloqueiam.
USER_AGENT = "Mozilla/5.0 (compatible; TikTokGameNews/1.0; leitor de feeds pessoal)"
DEFAULT_TIMEOUT = 20


@dataclass
class FeedResult:
    """Resultado de uma busca: itens novos + o que guardar pro próximo GET."""

    items: list[NewsItem]
    status: int | None
    etag: str | None
    modified: str | None

    @property
    def not_modified(self) -> bool:
        return self.status == 304


def fetch_feed(
    url: str,
    source_name: str,
    etag: str | None = None,
    modified: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> FeedResult:
    """Busca e parseia um feed, mandando ETag/Last-Modified da última vez.

    Levanta exceção se o feed não puder ser lido (o chamador decide se isso
    derruba a rodada — em collector/run.py, não derruba: pula a fonte).
    """
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified

    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code == 304:
        return FeedResult(items=[], status=304, etag=etag, modified=modified)
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Falha ao parsear feed em {url}: {parsed.bozo_exception}")

    return FeedResult(
        items=_entries_to_items(parsed, source_name),
        status=response.status_code,
        etag=response.headers.get("ETag") or etag,
        modified=response.headers.get("Last-Modified") or modified,
    )


def _struct_time_to_datetime(t: struct_time | None) -> datetime | None:
    if t is None:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc)


def parse_feed(raw_content: str | bytes, source_name: str) -> list[NewsItem]:
    """Parseia o conteúdo bruto (string/bytes) de um feed em uma lista de NewsItem.

    `raw_content` pode ser o próprio texto XML do feed (usado em testes)
    ou uma URL (feedparser aceita ambos).
    """
    return _entries_to_items(feedparser.parse(raw_content), source_name)


def _entries_to_items(parsed, source_name: str) -> list[NewsItem]:
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
