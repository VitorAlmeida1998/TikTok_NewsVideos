"""Testes do orquestrador dedupe/run.py contra um SQLite temporário."""
from shared.db import get_connection, get_relevant_items, save_item
from shared.models import NewsItem
from dedupe.run import run


def make_item(title: str, url: str) -> NewsItem:
    return NewsItem(
        title=title,
        source="sample",
        url=url,
        published_at=None,
        summary="",
    )


def test_run_marks_relevant_and_irrelevant_items(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        save_item(conn, make_item("Big Sequel Leaked Online", "https://example.com/1"))
        save_item(conn, make_item("A calm quiet day in gaming", "https://example.com/2"))
        save_item(conn, make_item("Studio Announces Exclusive Deal", "https://example.com/3"))

    total_evaluated, total_relevant = run(db_path=tmp_db_path)

    assert total_evaluated == 3
    assert total_relevant == 2

    with get_connection(tmp_db_path) as conn:
        relevant_titles = {row["title"] for row in get_relevant_items(conn)}
        assert relevant_titles == {
            "Big Sequel Leaked Online",
            "Studio Announces Exclusive Deal",
        }


def test_run_is_idempotent_skips_already_evaluated(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        save_item(conn, make_item("Big Sequel Leaked Online", "https://example.com/1"))

    first_evaluated, _ = run(db_path=tmp_db_path)
    second_evaluated, _ = run(db_path=tmp_db_path)

    assert first_evaluated == 1
    assert second_evaluated == 0  # já avaliado, não reprocessa


def test_run_with_no_pending_items(tmp_db_path):
    total_evaluated, total_relevant = run(db_path=tmp_db_path)
    assert total_evaluated == 0
    assert total_relevant == 0


def test_run_rescore_reevaluates_already_evaluated_items(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        save_item(conn, make_item("Big Sequel Leaked Online", "https://example.com/1"))
    run(db_path=tmp_db_path)

    with get_connection(tmp_db_path) as conn:
        conn.execute("UPDATE news_items SET relevance_score = NULL")

    evaluated, relevant = run(db_path=tmp_db_path, rescore=True)
    assert (evaluated, relevant) == (1, 1)
    with get_connection(tmp_db_path) as conn:
        assert get_relevant_items(conn)[0]["relevance_score"] > 0
