"""Ponto de entrada do módulo dedupe: avalia relevância de itens já coletados.

O dedupe por conteúdo (título+URL) já acontece no momento da coleta
(shared/db.save_item, via UNIQUE content_hash). Este script cuida da segunda
etapa do pipeline: passar pelos itens ainda não avaliados e marcar quais são
relevantes com base em palavras-chave (leak, reveal, delay, launch, exclusive...).

Uso:
    uv run python -m dedupe.run [--db data/news.db]
"""
from __future__ import annotations

import argparse
import logging
import sys

from dedupe.keyword_filter import DEFAULT_KEYWORDS, find_matched_keywords
from shared.db import get_connection, get_unevaluated_items, mark_relevance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dedupe")


def run(db_path: str | None = None, keywords: list[str] | None = None) -> tuple[int, int]:
    """Avalia relevância de todos os itens ainda não avaliados.

    Retorna (total_avaliados, total_relevantes).
    """
    keywords = keywords if keywords is not None else DEFAULT_KEYWORDS

    with get_connection(db_path) as conn:
        pending = get_unevaluated_items(conn)
        logger.info("%d item(ns) pendente(s) de avaliação de relevância", len(pending))

        relevant_count = 0
        for row in pending:
            matched = find_matched_keywords(row["title"], row["summary"] or "", keywords)
            relevant = len(matched) > 0
            mark_relevance(conn, row["id"], relevant, matched)
            if relevant:
                relevant_count += 1
                logger.info("RELEVANTE [%s] %s -> %s", row["source"], row["title"], matched)

        logger.info(
            "Dedupe finalizado: %d avaliados, %d relevantes", len(pending), relevant_count
        )
        return len(pending), relevant_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avalia relevância de itens coletados por palavras-chave"
    )
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    args = parser.parse_args()

    run(db_path=args.db)


if __name__ == "__main__":
    sys.exit(main() or 0)
