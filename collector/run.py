"""Ponto de entrada do módulo collector: busca feeds configurados e salva no SQLite.

Uso:
    uv run python -m collector.run [--feeds feeds.yaml] [--db data/news.db]
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from collector.feed_cache import load_cache, save_cache
from collector.feeds_config import DEFAULT_FEEDS_PATH, load_feeds
from collector.parser import fetch_feed
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

    cache = load_cache()
    total_new = 0
    unchanged = 0
    with get_connection(db_path) as conn:
        for feed in feeds:
            entry = cache.get(feed.url, {})
            try:
                result = fetch_feed(
                    feed.url,
                    feed.name,
                    etag=entry.get("etag"),
                    modified=entry.get("modified"),
                )
            except Exception:
                logger.exception("Erro ao coletar feed '%s' (%s)", feed.name, feed.url)
                continue

            cache[feed.url] = {"etag": result.etag, "modified": result.modified}
            if result.not_modified:
                unchanged += 1
                continue

            new_count = save_items(conn, result.items)
            total_new += new_count
            if new_count:
                logger.info(
                    "Feed '%s': %d itens no feed, %d novos", feed.name, len(result.items), new_count
                )

    save_cache(cache)
    logger.info(
        "Coleta finalizada: %d itens novos salvos (%d feed(s) sem novidade)", total_new, unchanged
    )
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
