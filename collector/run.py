"""Ponto de entrada do módulo collector: busca feeds configurados e salva no SQLite.

Uso:
    uv run python -m collector.run [--feeds feeds.yaml] [--db data/news.db]
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from collector.feeds_config import DEFAULT_FEEDS_PATH, load_feeds
from collector.parser import parse_feed
from shared.db import get_connection, save_items

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("collector")


def run(feeds_path: str = DEFAULT_FEEDS_PATH, db_path: str | None = None) -> int:
    """Executa uma rodada de coleta. Retorna o total de itens novos salvos."""
    feeds = load_feeds(feeds_path)
    logger.info("Coletando %d feed(s) de %s", len(feeds), feeds_path)

    total_new = 0
    with get_connection(db_path) as conn:
        for feed in feeds:
            try:
                items = parse_feed(feed.url, feed.name)
            except Exception:
                logger.exception("Erro ao coletar feed '%s' (%s)", feed.name, feed.url)
                continue

            new_count = save_items(conn, items)
            total_new += new_count
            logger.info(
                "Feed '%s': %d itens encontrados, %d novos", feed.name, len(items), new_count
            )

    logger.info("Coleta finalizada: %d itens novos salvos", total_new)
    return total_new


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Coleta feeds RSS de notícias de games")
    parser.add_argument("--feeds", default=DEFAULT_FEEDS_PATH, help="Caminho do feeds.yaml")
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    args = parser.parse_args()

    run(feeds_path=args.feeds, db_path=args.db)


if __name__ == "__main__":
    sys.exit(main() or 0)
