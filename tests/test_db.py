"""Testes de persistência no SQLite (dedupe por content_hash)."""
from datetime import datetime, timezone

from shared.db import get_connection, item_exists, save_item, save_items
from shared.models import NewsItem


def make_item(title="Some Title", url="https://example.com/a") -> NewsItem:
    return NewsItem(
        title=title,
        source="sample",
        url=url,
        published_at=datetime(2025, 9, 1, tzinfo=timezone.utc),
        summary="A summary",
    )


def test_save_item_inserts_new_item(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        item = make_item()
        inserted = save_item(conn, item)
        assert inserted is True
        assert item_exists(conn, item.content_hash) is True


def test_save_item_deduplicates_same_item(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        item = make_item()
        assert save_item(conn, item) is True
        assert save_item(conn, item) is False  # duplicado, ignorado

        count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        assert count == 1


def test_save_items_returns_count_of_new_only(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        item1 = make_item(title="Title 1", url="https://example.com/1")
        item2 = make_item(title="Title 2", url="https://example.com/2")

        first_batch = save_items(conn, [item1, item2])
        assert first_batch == 2

        second_batch = save_items(conn, [item1, item2])
        assert second_batch == 0


def test_item_exists_false_for_unknown_hash(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        assert item_exists(conn, "nonexistent-hash") is False


def test_get_unevaluated_items_returns_all_new_items(tmp_db_path):
    from shared.db import get_unevaluated_items

    with get_connection(tmp_db_path) as conn:
        item1 = make_item(title="Title 1", url="https://example.com/1")
        item2 = make_item(title="Title 2", url="https://example.com/2")
        save_items(conn, [item1, item2])

        pending = get_unevaluated_items(conn)
        assert len(pending) == 2


def test_mark_relevance_updates_item_and_removes_from_pending(tmp_db_path):
    from shared.db import get_unevaluated_items, mark_relevance

    with get_connection(tmp_db_path) as conn:
        item = make_item()
        save_item(conn, item)
        row_id = conn.execute(
            "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
        ).fetchone()[0]

        mark_relevance(conn, row_id, True, ["leak", "reveal"])

        assert get_unevaluated_items(conn) == []

        updated = conn.execute(
            "SELECT is_relevant, matched_keywords FROM news_items WHERE id = ?", (row_id,)
        ).fetchone()
        assert updated[0] == 1
        assert updated[1] == "leak,reveal"


def test_get_relevant_items_only_returns_marked_relevant(tmp_db_path):
    from shared.db import get_relevant_items, mark_relevance

    with get_connection(tmp_db_path) as conn:
        item1 = make_item(title="Relevant", url="https://example.com/rel")
        item2 = make_item(title="Not relevant", url="https://example.com/norel")
        save_items(conn, [item1, item2])

        id1 = conn.execute(
            "SELECT id FROM news_items WHERE content_hash = ?", (item1.content_hash,)
        ).fetchone()[0]
        id2 = conn.execute(
            "SELECT id FROM news_items WHERE content_hash = ?", (item2.content_hash,)
        ).fetchone()[0]

        mark_relevance(conn, id1, True, ["leak"])
        mark_relevance(conn, id2, False, [])

        relevant = get_relevant_items(conn)
        assert len(relevant) == 1
        assert relevant[0]["title"] == "Relevant"
