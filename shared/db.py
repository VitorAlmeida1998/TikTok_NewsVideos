"""Acesso ao SQLite compartilhado (dedupe e histórico de notícias coletadas)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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

# Colunas adicionadas após o schema inicial (migração leve, idempotente).
# Cada entrada: (nome_coluna, definição SQL para ALTER TABLE ... ADD COLUMN)
MIGRATIONS: list[tuple[str, str]] = [
    ("is_relevant", "is_relevant INTEGER"),
    ("matched_keywords", "matched_keywords TEXT"),
    ("relevance_checked_at", "relevance_checked_at TEXT"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    existing_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(news_items)").fetchall()
    }
    for col_name, column_def in MIGRATIONS:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE news_items ADD COLUMN {column_def}")


def get_db_path() -> str:
    return os.environ.get("DB_PATH", DEFAULT_DB_PATH)


@contextmanager
def get_connection(db_path: str | None = None):
    path = db_path or get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
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


def get_unevaluated_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Retorna itens ainda não avaliados quanto à relevância (is_relevant IS NULL)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM news_items WHERE is_relevant IS NULL ORDER BY collected_at"
    ).fetchall()
    return rows


def mark_relevance(
    conn: sqlite3.Connection,
    item_id: int,
    is_relevant: bool,
    matched_keywords: list[str],
) -> None:
    """Grava o resultado da avaliação de relevância para um item já salvo."""
    conn.execute(
        """
        UPDATE news_items
        SET is_relevant = ?, matched_keywords = ?, relevance_checked_at = ?
        WHERE id = ?
        """,
        (
            1 if is_relevant else 0,
            ",".join(matched_keywords),
            datetime.now(timezone.utc).isoformat(),
            item_id,
        ),
    )


def get_relevant_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Retorna itens já marcados como relevantes."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM news_items WHERE is_relevant = 1 ORDER BY collected_at"
    ).fetchall()
    return rows
