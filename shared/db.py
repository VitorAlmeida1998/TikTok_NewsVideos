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
    ("script_hook", "script_hook TEXT"),
    ("script_body", "script_body TEXT"),
    ("script_cta", "script_cta TEXT"),
    ("script_model", "script_model TEXT"),
    ("script_generated_at", "script_generated_at TEXT"),
    ("game_name", "game_name TEXT"),
    ("audio_path", "audio_path TEXT"),
    ("video_spec_path", "video_spec_path TEXT"),
    ("video_path", "video_path TEXT"),
    ("video_generated_at", "video_generated_at TEXT"),
    ("tiktok_published_at", "tiktok_published_at TEXT"),
    ("tiktok_publish_id", "tiktok_publish_id TEXT"),
    ("publish_status", "publish_status TEXT"),
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


def get_items_pending_script(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Itens relevantes que ainda não têm roteiro gerado."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM news_items
        WHERE is_relevant = 1 AND script_body IS NULL
        ORDER BY collected_at
        """
    ).fetchall()
    return rows


def save_script(
    conn: sqlite3.Connection,
    item_id: int,
    hook: str,
    body: str,
    cta: str,
    model: str,
    game_name: str = "",
) -> None:
    """Grava o roteiro gerado (hook + corpo + call-to-action) para um item."""
    conn.execute(
        """
        UPDATE news_items
        SET script_hook = ?, script_body = ?, script_cta = ?,
            script_model = ?, script_generated_at = ?, game_name = ?
        WHERE id = ?
        """,
        (hook, body, cta, model, datetime.now(timezone.utc).isoformat(), game_name, item_id),
    )


def get_items_with_script(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Itens que já têm roteiro pronto (prontos para video_gen)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM news_items
        WHERE script_body IS NOT NULL
        ORDER BY collected_at
        """
    ).fetchall()
    return rows


def get_items_pending_video(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Itens com roteiro pronto que ainda não têm vídeo gerado."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM news_items
        WHERE script_body IS NOT NULL AND video_path IS NULL
        ORDER BY collected_at
        """
    ).fetchall()
    return rows


def save_video(
    conn: sqlite3.Connection,
    item_id: int,
    audio_path: str,
    video_spec_path: str,
    video_path: str | None,
) -> None:
    """Grava os artefatos gerados pelo video_gen para um item."""
    conn.execute(
        """
        UPDATE news_items
        SET audio_path = ?, video_spec_path = ?, video_path = ?, video_generated_at = ?
        WHERE id = ?
        """,
        (
            audio_path,
            video_spec_path,
            video_path,
            datetime.now(timezone.utc).isoformat(),
            item_id,
        ),
    )


def get_items_with_video(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Itens que já têm vídeo renderizado (prontos para publisher)."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM news_items
        WHERE video_path IS NOT NULL
        ORDER BY collected_at
        """
    ).fetchall()
    return rows


def get_items_pending_publish(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Itens com vídeo pronto que ainda não foram publicados no TikTok."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM news_items
        WHERE video_path IS NOT NULL AND tiktok_published_at IS NULL
        ORDER BY collected_at
        """
    ).fetchall()
    return rows


def save_publish_result(
    conn: sqlite3.Connection, item_id: int, publish_id: str, status: str
) -> None:
    """Grava o resultado de uma tentativa de publicação no TikTok."""
    conn.execute(
        """
        UPDATE news_items
        SET tiktok_publish_id = ?, publish_status = ?, tiktok_published_at = ?
        WHERE id = ?
        """,
        (publish_id, status, datetime.now(timezone.utc).isoformat(), item_id),
    )


# --- Helpers para o front-end (webapp/) ---------------------------------


def get_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    """Retorna um único item pelo id, ou None se não existir."""
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM news_items WHERE id = ?", (item_id,)).fetchone()


def list_items(
    conn: sqlite3.Connection,
    status: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Lista itens com filtro opcional por status derivado e busca por título.

    status aceito: "relevant" (is_relevant=1), "not_relevant" (is_relevant=0),
    "unevaluated" (is_relevant IS NULL), "scripted" (tem roteiro),
    "video_ready" (tem vídeo), "pending_script" (relevante sem roteiro),
    "pending_video" (com roteiro sem vídeo). None = todos.
    """
    conn.row_factory = sqlite3.Row
    clauses = []
    params: list = []

    status_clauses = {
        "relevant": "is_relevant = 1",
        "not_relevant": "is_relevant = 0",
        "unevaluated": "is_relevant IS NULL",
        "scripted": "script_body IS NOT NULL",
        "video_ready": "video_path IS NOT NULL",
        "pending_script": "is_relevant = 1 AND script_body IS NULL",
        "pending_video": "script_body IS NOT NULL AND video_path IS NULL",
    }
    if status and status in status_clauses:
        clauses.append(status_clauses[status])

    if search:
        clauses.append("(title LIKE ? OR game_name LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT * FROM news_items
        {where}
        ORDER BY collected_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    return conn.execute(query, params).fetchall()


def count_items(conn: sqlite3.Connection, status: str | None = None, search: str | None = None) -> int:
    """Conta itens com o mesmo filtro usado em list_items (para paginação)."""
    clauses = []
    params: list = []

    status_clauses = {
        "relevant": "is_relevant = 1",
        "not_relevant": "is_relevant = 0",
        "unevaluated": "is_relevant IS NULL",
        "scripted": "script_body IS NOT NULL",
        "video_ready": "video_path IS NOT NULL",
        "pending_script": "is_relevant = 1 AND script_body IS NULL",
        "pending_video": "script_body IS NOT NULL AND video_path IS NULL",
    }
    if status and status in status_clauses:
        clauses.append(status_clauses[status])

    if search:
        clauses.append("(title LIKE ? OR game_name LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    row = conn.execute(f"SELECT COUNT(*) FROM news_items {where}", params).fetchone()
    return row[0]


def get_status_counts(conn: sqlite3.Connection) -> dict:
    """Retorna contagens por status, para badges/filtros no dashboard."""
    conn.row_factory = sqlite3.Row
    counts = {}
    counts["total"] = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
    counts["relevant"] = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE is_relevant = 1"
    ).fetchone()[0]
    counts["unevaluated"] = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE is_relevant IS NULL"
    ).fetchone()[0]
    counts["pending_script"] = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE is_relevant = 1 AND script_body IS NULL"
    ).fetchone()[0]
    counts["pending_video"] = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE script_body IS NOT NULL AND video_path IS NULL"
    ).fetchone()[0]
    counts["video_ready"] = conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE video_path IS NOT NULL"
    ).fetchone()[0]
    return counts


def update_script(
    conn: sqlite3.Connection, item_id: int, hook: str, body: str, cta: str, game_name: str
) -> None:
    """Atualiza manualmente o roteiro de um item (edição pelo usuário no front-end)."""
    conn.execute(
        """
        UPDATE news_items
        SET script_hook = ?, script_body = ?, script_cta = ?, game_name = ?
        WHERE id = ?
        """,
        (hook, body, cta, game_name, item_id),
    )


def clear_video(conn: sqlite3.Connection, item_id: int) -> None:
    """Limpa os campos de vídeo de um item, para forçar regeneração."""
    conn.execute(
        """
        UPDATE news_items
        SET audio_path = NULL, video_spec_path = NULL, video_path = NULL,
            video_generated_at = NULL
        WHERE id = ?
        """,
        (item_id,),
    )
