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

from dotenv import load_dotenv

from dedupe.keyword_filter import DEFAULT_KEYWORDS, find_matched_keywords, relevance_score
from dedupe.story_group import GROUP_WINDOW_HOURS, find_story_group
from shared.db import (
    get_all_items,
    get_connection,
    get_story_candidates,
    get_unevaluated_items,
    mark_relevance,
    set_story_group,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dedupe")


def run(
    db_path: str | None = None, keywords: list[str] | None = None, rescore: bool = False
) -> tuple[int, int]:
    """Avalia relevância de todos os itens ainda não avaliados.

    `rescore=True` reavalia TODOS os itens (útil depois de mudar pesos/keywords).
    Retorna (total_avaliados, total_relevantes).
    """
    keywords = keywords if keywords is not None else DEFAULT_KEYWORDS

    with get_connection(db_path) as conn:
        pending = get_all_items(conn) if rescore else get_unevaluated_items(conn)
        logger.info("%d item(ns) pendente(s) de avaliação de relevância", len(pending))

        relevant_count = 0
        grouped_count = 0
        for row in pending:
            summary = row["summary"] or ""
            matched = find_matched_keywords(row["title"], summary, keywords)
            relevant = len(matched) > 0
            score = relevance_score(row["title"], summary, row["source"], matched)
            mark_relevance(conn, row["id"], relevant, matched, score=score)

            # Mesma história coberta por vários feeds: agrupa para o pipeline
            # gerar um vídeo só (ver dedupe/story_group.py).
            candidates = get_story_candidates(conn, GROUP_WINDOW_HOURS, exclude_id=row["id"])
            group = find_story_group(
                row["title"], [(c["id"], c["title"], c["story_group"]) for c in candidates]
            )
            set_story_group(conn, row["id"], group if group is not None else row["id"])

            if relevant:
                relevant_count += 1
                if group is not None:
                    grouped_count += 1
                    logger.info(
                        "RELEVANTE (score %.1f) [%s] %s -> %s | mesma história do item #%s",
                        score, row["source"], row["title"], matched, group,
                    )
                else:
                    logger.info(
                        "RELEVANTE (score %.1f) [%s] %s -> %s",
                        score, row["source"], row["title"], matched,
                    )

        logger.info(
            "Dedupe finalizado: %d avaliados, %d relevantes (%d repetiam história já coberta)",
            len(pending),
            relevant_count,
            grouped_count,
        )
        return len(pending), relevant_count


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Avalia relevância de itens coletados por palavras-chave"
    )
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument(
        "--rescore", action="store_true", help="Reavalia todos os itens (após mudar pesos/keywords)"
    )
    args = parser.parse_args()

    run(db_path=args.db, rescore=args.rescore)


if __name__ == "__main__":
    sys.exit(main() or 0)
