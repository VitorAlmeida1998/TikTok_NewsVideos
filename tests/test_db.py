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
