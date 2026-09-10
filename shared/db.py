"""Acesso ao SQLite compartilhado (dedupe e histórico de notícias coletadas)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
    ("relevance_score", "relevance_score REAL"),
    ("story_group", "story_group INTEGER"),
    ("script_hook", "script_hook TEXT"),
    ("script_body", "script_body TEXT"),
    ("script_cta", "script_cta TEXT"),
    ("script_description", "script_description TEXT"),
    ("script_pronunciations", "script_pronunciations TEXT"),
    ("script_model", "script_model TEXT"),
    ("script_generated_at", "script_generated_at TEXT"),
    ("game_name", "game_name TEXT"),
    ("audio_path", "audio_path TEXT"),
    ("video_spec_path", "video_spec_path TEXT"),
    ("video_path", "video_path TEXT"),
    ("video_generated_at", "video_generated_at TEXT"),
    ("video_skip_reason", "video_skip_reason TEXT"),
    ("cover_path", "cover_path TEXT"),
    ("publish_scheduled_at", "publish_scheduled_at TEXT"),
    ("posted_at", "posted_at TEXT"),
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
    # timeout maior + WAL: a webapp permite disparar várias ações em paralelo
    # (collector, bulk script/video, ações por item), e algumas mantêm a
    # conexão aberta por dezenas de segundos (ex: collector.run faz várias
    # chamadas de rede antes do commit final). Sem isso, duas escritas
    # concorrentes facilmente batem em "database is locked" com o timeout
    # padrão de 5s. WAL permite leitores não bloquearem o escritor atual.
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
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


def get_all_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM news_items ORDER BY collected_at").fetchall()


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
    score: float = 0.0,
) -> None:
    """Grava o resultado da avaliação de relevância para um item já salvo."""
    conn.execute(
        """
        UPDATE news_items
        SET is_relevant = ?, matched_keywords = ?, relevance_score = ?, relevance_checked_at = ?
        WHERE id = ?
        """,
        (
            1 if is_relevant else 0,
            ",".join(matched_keywords),
            score,
            datetime.now(timezone.utc).isoformat(),
            item_id,
        ),
    )


def _max_age_clause(max_age_hours: float | None) -> tuple[str, list]:
    """Filtro opcional "só notícias coletadas nas últimas N horas" — evita gastar
    créditos de TTS/tempo de render com notícia velha quando o pipeline roda sozinho."""
    if max_age_hours is None:
        return "", []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return " AND collected_at >= ?", [cutoff.isoformat()]


# Pontuação efetiva = relevância x frescor. O decaimento fica no SQL (e não
# congelado na coluna) porque a mesma notícia perde valor a cada hora parada
# na fila — espelha dedupe.keyword_filter.freshness_multiplier.
EFFECTIVE_SCORE_SQL = (
    "COALESCE(relevance_score, 0) * "
    "MAX(0.15, 1.0 - ((julianday('now') - julianday(collected_at)) * 24.0) / 72.0)"
)

# Ordem de processamento quando há limite por rodada: maior pontuação efetiva
# primeiro, empate resolvido pela notícia mais recente.
PRIORITY_ORDER = f"ORDER BY {EFFECTIVE_SCORE_SQL} DESC, collected_at DESC"

# Um vídeo por história: se outro item do mesmo `story_group` já virou
# roteiro/vídeo, este é uma cobertura repetida do mesmo fato (ver
# dedupe/story_group.py) e não deve gerar um segundo vídeo.
_NO_DUPLICATE_STORY = """
    AND NOT EXISTS (
        SELECT 1 FROM news_items AS other
        WHERE other.id != news_items.id
          AND other.story_group IS NOT NULL
          AND other.story_group = news_items.story_group
          AND other.{column} IS NOT NULL
    )
"""


def get_relevant_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Retorna itens já marcados como relevantes."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM news_items WHERE is_relevant = 1 ORDER BY collected_at"
    ).fetchall()
    return rows


def get_items_pending_script(
    conn: sqlite3.Connection, max_age_hours: float | None = None
) -> list[sqlite3.Row]:
    """Itens relevantes que ainda não têm roteiro gerado, mais relevantes primeiro."""
    conn.row_factory = sqlite3.Row
    age_clause, params = _max_age_clause(max_age_hours)
    rows = conn.execute(
        f"""
        SELECT *, {EFFECTIVE_SCORE_SQL} AS effective_score FROM news_items
        WHERE is_relevant = 1 AND script_body IS NULL{age_clause}
        {_NO_DUPLICATE_STORY.format(column="script_body")}
        {PRIORITY_ORDER}
        """,
        params,
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
    description: str = "",
    pronunciations: str = "",
) -> None:
    """Grava o roteiro gerado (hook + corpo + call-to-action + descrição/hashtags
    + respellings de pronúncia) para um item."""
    conn.execute(
        """
        UPDATE news_items
        SET script_hook = ?, script_body = ?, script_cta = ?, script_description = ?,
            script_pronunciations = ?, script_model = ?, script_generated_at = ?, game_name = ?
        WHERE id = ?
        """,
        (
            hook,
            body,
            cta,
            description,
            pronunciations,
            model,
            datetime.now(timezone.utc).isoformat(),
            game_name,
            item_id,
        ),
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


def get_items_pending_video(
    conn: sqlite3.Connection, max_age_hours: float | None = None
) -> list[sqlite3.Row]:
    """Itens com roteiro pronto que ainda não têm vídeo gerado, mais relevantes primeiro."""
    conn.row_factory = sqlite3.Row
    age_clause, params = _max_age_clause(max_age_hours)
    rows = conn.execute(
        f"""
        SELECT *, {EFFECTIVE_SCORE_SQL} AS effective_score FROM news_items
        WHERE script_body IS NOT NULL AND video_path IS NULL{age_clause}
        {_NO_DUPLICATE_STORY.format(column="video_path")}
        {PRIORITY_ORDER}
        """,
        params,
    ).fetchall()
    return rows


def count_videos_generated_since(
    conn: sqlite3.Connection, hours: float | None = None, since: datetime | None = None
) -> int:
    """Quantos vídeos foram gerados desde `since` (ou nas últimas `hours`).

    O teto diário conta por DIA DE CALENDÁRIO, não por janela deslizante de
    24h: com janela deslizante, um lote gerado ontem à noite continua
    bloqueando a manhã seguinte.
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=hours or 24)
    return conn.execute(
        "SELECT COUNT(*) FROM news_items WHERE video_generated_at >= ?",
        (since.astimezone(timezone.utc).isoformat(),),
    ).fetchone()[0]


def set_video_skip_reason(conn: sqlite3.Connection, item_id: int, reason: str) -> None:
    """Marca por que o item foi pulado na geração automática (ex: sem vídeo de
    fundo/música) — aparece no painel como "aguardando mídia"."""
    conn.execute(
        "UPDATE news_items SET video_skip_reason = ? WHERE id = ?", (reason, item_id)
    )


def save_video(
    conn: sqlite3.Connection,
    item_id: int,
    audio_path: str,
    video_spec_path: str,
    video_path: str | None,
    cover_path: str | None = None,
) -> None:
    """Grava os artefatos gerados pelo video_gen para um item."""
    conn.execute(
        """
        UPDATE news_items
        SET audio_path = ?, video_spec_path = ?, video_path = ?, cover_path = ?,
            video_generated_at = ?, video_skip_reason = NULL
        WHERE id = ?
        """,
        (
            audio_path,
            video_spec_path,
            video_path,
            cover_path,
            datetime.now(timezone.utc).isoformat(),
            item_id,
        ),
    )


def set_story_group(conn: sqlite3.Connection, item_id: int, story_group: int) -> None:
    """Marca a qual história (grupo de notícias sobre o mesmo fato) o item pertence."""
    conn.execute("UPDATE news_items SET story_group = ? WHERE id = ?", (story_group, item_id))


def get_story_candidates(
    conn: sqlite3.Connection, window_hours: float, exclude_id: int | None = None
) -> list[sqlite3.Row]:
    """Itens já avaliados dentro da janela, do mais recente pro mais antigo —
    entrada de dedupe.story_group.find_story_group."""
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    return conn.execute(
        """
        SELECT id, title, story_group FROM news_items
        WHERE collected_at >= ? AND is_relevant IS NOT NULL AND id != COALESCE(?, -1)
        ORDER BY collected_at DESC
        """,
        (cutoff, exclude_id),
    ).fetchall()


def get_story_siblings(conn: sqlite3.Connection, item_id: int) -> list[sqlite3.Row]:
    """Outras notícias da MESMA história (para o painel avisar 'já virou vídeo
    no item #X')."""
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, title, source, video_path, script_body FROM news_items
        WHERE story_group IS NOT NULL
          AND story_group = (SELECT story_group FROM news_items WHERE id = ?)
          AND id != ?
        ORDER BY collected_at
        """,
        (item_id, item_id),
    ).fetchall()


def get_recent_hooks(conn: sqlite3.Connection, limit: int = 10) -> list[str]:
    """Hooks dos últimos roteiros — usados para o script_gen não repetir sempre
    a mesma abertura."""
    rows = conn.execute(
        """
        SELECT script_hook FROM news_items
        WHERE script_hook IS NOT NULL AND script_hook != ''
        ORDER BY script_generated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row[0] for row in rows]


# --- Fila de publicação ----------------------------------------------------


def get_publish_queue(conn: sqlite3.Connection, include_posted: bool = False) -> list[sqlite3.Row]:
    """Vídeos prontos ainda não postados, na ordem em que devem ir pro ar
    (agendados primeiro, depois por pontuação efetiva)."""
    conn.row_factory = sqlite3.Row
    where = "video_path IS NOT NULL" if include_posted else "video_path IS NOT NULL AND posted_at IS NULL"
    return conn.execute(
        f"""
        SELECT *, {EFFECTIVE_SCORE_SQL} AS effective_score,
               (julianday('now') - julianday(collected_at)) * 24.0 AS age_hours
        FROM news_items
        WHERE {where}
        ORDER BY posted_at IS NOT NULL,
                 publish_scheduled_at IS NULL,
                 publish_scheduled_at,
                 {EFFECTIVE_SCORE_SQL} DESC
        """
    ).fetchall()


def schedule_publish(conn: sqlite3.Connection, item_id: int, when: datetime | None) -> None:
    """Define (ou limpa, com None) o horário sugerido de publicação."""
    conn.execute(
        "UPDATE news_items SET publish_scheduled_at = ? WHERE id = ?",
        (when.isoformat() if when else None, item_id),
    )


def mark_posted(conn: sqlite3.Connection, item_id: int, posted: bool = True) -> None:
    """Marca/desmarca que o vídeo já foi publicado manualmente no TikTok."""
    conn.execute(
        "UPDATE news_items SET posted_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat() if posted else None, item_id),
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


STATUS_CLAUSES = {
    "relevant": "is_relevant = 1",
    "not_relevant": "is_relevant = 0",
    "unevaluated": "is_relevant IS NULL",
    "scripted": "script_body IS NOT NULL",
    "video_ready": "video_path IS NOT NULL",
    "pending_script": "is_relevant = 1 AND script_body IS NULL",
    "pending_video": "script_body IS NOT NULL AND video_path IS NULL",
    "awaiting_media": (
        "script_body IS NOT NULL AND video_path IS NULL AND video_skip_reason IS NOT NULL"
    ),
    "to_post": "video_path IS NOT NULL AND posted_at IS NULL",
    "posted": "posted_at IS NOT NULL",
}

# Filtros de "fila de trabalho" são listados na mesma ordem em que o pipeline
# automático vai processar (mais relevante primeiro); o resto, mais recente primeiro.
_PRIORITY_ORDERED_STATUSES = {
    "relevant", "pending_script", "pending_video", "awaiting_media", "to_post",
}


def _build_filter(status: str | None, search: str | None) -> tuple[str, list]:
    clauses = []
    params: list = []
    if status and status in STATUS_CLAUSES:
        clauses.append(STATUS_CLAUSES[status])
    if search:
        clauses.append("(title LIKE ? OR game_name LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def list_items(
    conn: sqlite3.Connection,
    status: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Lista itens com filtro opcional por status derivado (chaves de
    STATUS_CLAUSES; None = todos) e busca por título/jogo."""
    conn.row_factory = sqlite3.Row
    where, params = _build_filter(status, search)
    order = PRIORITY_ORDER if status in _PRIORITY_ORDERED_STATUSES else "ORDER BY collected_at DESC"
    query = f"""
        SELECT * FROM news_items
        {where}
        {order}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    return conn.execute(query, params).fetchall()


def count_items(conn: sqlite3.Connection, status: str | None = None, search: str | None = None) -> int:
    """Conta itens com o mesmo filtro usado em list_items (para paginação)."""
    where, params = _build_filter(status, search)
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
    for key in ("awaiting_media", "to_post", "posted"):
        counts[key] = conn.execute(
            f"SELECT COUNT(*) FROM news_items WHERE {STATUS_CLAUSES[key]}"
        ).fetchone()[0]
    return counts


def update_script(
    conn: sqlite3.Connection,
    item_id: int,
    hook: str,
    body: str,
    cta: str,
    game_name: str,
    description: str = "",
    pronunciations: str = "",
) -> None:
    """Atualiza manualmente o roteiro de um item (edição pelo usuário no front-end)."""
    conn.execute(
        """
        UPDATE news_items
        SET script_hook = ?, script_body = ?, script_cta = ?, script_description = ?,
            script_pronunciations = ?, game_name = ?
        WHERE id = ?
        """,
        (hook, body, cta, description, pronunciations, game_name, item_id),
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
