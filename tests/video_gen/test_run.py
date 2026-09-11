"""Testes do orquestrador video_gen/run.py (mock de generate_video_for_item)."""
from unittest.mock import patch

from video_gen.run import run
from shared.db import (
    get_connection,
    get_items_with_video,
    mark_relevance,
    save_item,
    save_script,
)
from shared.models import NewsItem


def make_scripted_item(conn, title: str, url: str) -> int:
    item = NewsItem(title=title, source="sample", url=url, published_at=None, summary="resumo")
    save_item(conn, item)
    row_id = conn.execute(
        "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
    ).fetchone()[0]
    mark_relevance(conn, row_id, True, ["leak"])
    save_script(conn, row_id, hook="h", body="b", cta="c", model="m")
    return row_id


def _fake_result(row, render=True, require_media=False):
    result = {
        "item_id": row["id"],
        "audio_path": f"/tmp/audio_{row['id']}.mp3",
        "spec_path": f"/tmp/spec_{row['id']}.json",
    }
    if render:
        result["video_path"] = f"/tmp/video_{row['id']}.mp4"
    return result


def test_run_generates_videos_for_pending_items(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_scripted_item(conn, "Title A", "https://example.com/a")
        make_scripted_item(conn, "Title B", "https://example.com/b")

    with patch("video_gen.run.generate_video_for_item", side_effect=_fake_result):
        generated = run(db_path=tmp_db_path)

    assert generated == 2

    with get_connection(tmp_db_path) as conn:
        with_video = get_items_with_video(conn)
        assert len(with_video) == 2
        assert with_video[0]["video_path"].startswith("/tmp/video_")


def test_run_skips_items_already_with_video(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_scripted_item(conn, "Title A", "https://example.com/a")

    with patch("video_gen.run.generate_video_for_item", side_effect=_fake_result):
        first = run(db_path=tmp_db_path)
        second = run(db_path=tmp_db_path)

    assert first == 1
    assert second == 0


def test_run_continues_when_one_item_fails(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_scripted_item(conn, "Good", "https://example.com/good")
        make_scripted_item(conn, "Bad", "https://example.com/bad")

    def side_effect(row, render=True, require_media=False):
        if row["title"] == "Bad":
            raise RuntimeError("tts error")
        return _fake_result(row, render)

    with patch("video_gen.run.generate_video_for_item", side_effect=side_effect):
        generated = run(db_path=tmp_db_path)

    assert generated == 1
