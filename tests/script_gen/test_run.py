"""Testes do orquestrador script_gen/run.py (mock do generate_script, sem API real)."""
from unittest.mock import patch

from script_gen.run import run
from shared.db import get_connection, get_items_with_script, save_item, mark_relevance
from shared.models import NewsItem


def make_relevant_item(conn, title: str, url: str):
    item = NewsItem(title=title, source="sample", url=url, published_at=None, summary="resumo")
    save_item(conn, item)
    row_id = conn.execute(
        "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
    ).fetchone()[0]
    mark_relevance(conn, row_id, True, ["leak"])
    return row_id


def _fake_script(title, summary, source, model="m", client=None, recent_hooks=None):
    return {"hook": f"hook-{title}", "body": f"body-{title}", "cta": "cta"}


def test_run_generates_scripts_for_pending_relevant_items(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_relevant_item(conn, "Title A", "https://example.com/a")
        make_relevant_item(conn, "Title B", "https://example.com/b")

    with patch("script_gen.run.generate_script", side_effect=_fake_script):
        generated = run(db_path=tmp_db_path)

    assert generated == 2

    with get_connection(tmp_db_path) as conn:
        scripted = get_items_with_script(conn)
        assert len(scripted) == 2
        assert scripted[0]["script_hook"] == "hook-Title A"


def test_run_skips_items_already_scripted(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_relevant_item(conn, "Title A", "https://example.com/a")

    with patch("script_gen.run.generate_script", side_effect=_fake_script):
        first = run(db_path=tmp_db_path)
        second = run(db_path=tmp_db_path)

    assert first == 1
    assert second == 0


def test_run_continues_when_one_item_fails(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_relevant_item(conn, "Good Title", "https://example.com/good")
        make_relevant_item(conn, "Bad Title", "https://example.com/bad")

    def side_effect(title, summary, source, model="m", client=None, recent_hooks=None):
        if title == "Bad Title":
            raise RuntimeError("API error")
        return _fake_script(title, summary, source)

    with patch("script_gen.run.generate_script", side_effect=side_effect):
        generated = run(db_path=tmp_db_path)

    assert generated == 1


def test_run_respects_limit(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        for i in range(5):
            make_relevant_item(conn, f"Title {i}", f"https://example.com/{i}")

    with patch("script_gen.run.generate_script", side_effect=_fake_script):
        generated = run(db_path=tmp_db_path, limit=2)

    assert generated == 2
