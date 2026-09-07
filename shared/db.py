"""Acesso ao SQLite compartilhado (dedupe e histórico de notícias coletadas)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from shared.models import NewsItem

DEFAULT_DB_PATH = "data/news.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT,
    summary TEXT,
    collected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_items_source ON news_items(source);
CREATE INDEX IF NOT EXISTS idx_news_items_collected_at ON news_items(collected_at);
"""


def get_db_path() -> str:
    return os.environ.get("DB_PATH", DEFAULT_DB_PATH)


@contextmanager
def get_connection(db_path: str | None = None):
    path = db_path or get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_item(conn: sqlite3.Connection, item: NewsItem) -> bool:
    """Insere um NewsItem se ainda não existir (dedupe por content_hash).

    Retorna True se um novo registro foi inserido, False se já existia.
    """
    data = item.to_dict()
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO news_items
            (content_hash, title, source, url, published_at, summary, collected_at)
        VALUES (:content_hash, :title, :source, :url, :published_at, :summary, :collected_at)
        """,
        data,
    )
    return cursor.rowcount > 0


def save_items(conn: sqlite3.Connection, items: list[NewsItem]) -> int:
    """Salva vários itens, retornando quantos foram efetivamente inseridos (novos)."""
    return sum(save_item(conn, item) for item in items)


def item_exists(conn: sqlite3.Connection, content_hash: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM news_items WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    return row is not None
