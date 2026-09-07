"""Testes do orquestrador publisher/run.py (dry-run por padrão, mocks para modo live)."""
from unittest.mock import patch

from publisher.run import run
from shared.db import (
    get_connection,
    mark_relevance,
    save_item,
    save_script,
    save_video,
)
from shared.models import NewsItem


def make_video_ready_item(conn, title: str, url: str) -> int:
    item = NewsItem(title=title, source="sample", url=url, published_at=None, summary="r")
    save_item(conn, item)
    row_id = conn.execute(
        "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
    ).fetchone()[0]
    mark_relevance(conn, row_id, True, ["leak"])
    save_script(conn, row_id, hook="h", body="b", cta="c", model="m")
    save_video(conn, row_id, audio_path="/tmp/a.mp3", video_spec_path="/tmp/s.json", video_path="/tmp/v.mp4")
    return row_id


def test_dry_run_does_not_call_tiktok_api(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_video_ready_item(conn, "Title A", "https://example.com/a")

    with patch("publisher.run.post_video_to_inbox") as mock_post:
        processed = run(db_path=tmp_db_path, dry_run=True)

    assert processed == 1
    mock_post.assert_not_called()


def test_dry_run_marks_items_as_dry_run_status(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_video_ready_item(conn, "Title A", "https://example.com/a")

    run(db_path=tmp_db_path, dry_run=True)

    with get_connection(tmp_db_path) as conn:
        row = conn.execute("SELECT publish_status FROM news_items").fetchone()
        assert row[0] == "dry_run"


def test_live_mode_calls_post_video_to_inbox(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_video_ready_item(conn, "Title A", "https://example.com/a")

    with patch(
        "publisher.run.post_video_to_inbox",
        return_value={"data": {"publish_id": "pub999"}},
    ) as mock_post:
        processed = run(db_path=tmp_db_path, dry_run=False, mode="inbox")

    assert processed == 1
    mock_post.assert_called_once()

    with get_connection(tmp_db_path) as conn:
        row = conn.execute(
            "SELECT tiktok_publish_id, publish_status FROM news_items"
        ).fetchone()
        assert row[0] == "pub999"
        assert row[1] == "submitted"


def test_run_skips_already_published_items(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        make_video_ready_item(conn, "Title A", "https://example.com/a")

    first = run(db_path=tmp_db_path, dry_run=True)
    second = run(db_path=tmp_db_path, dry_run=True)

    assert first == 1
    assert second == 0


def test_run_continues_when_one_item_fails_in_live_mode(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        id_good = make_video_ready_item(conn, "Good", "https://example.com/good")
        id_bad = make_video_ready_item(conn, "Bad", "https://example.com/bad")
        # dá paths de vídeo distintos por item, para diferenciar no side_effect
        conn.execute(
            "UPDATE news_items SET video_path = ? WHERE id = ?", ("/tmp/good.mp4", id_good)
        )
        conn.execute(
            "UPDATE news_items SET video_path = ? WHERE id = ?", ("/tmp/bad.mp4", id_bad)
        )

    from publisher.tiktok_client import PublisherError

    def side_effect(video_path):
        if video_path == "/tmp/good.mp4":
            return {"data": {"publish_id": "ok"}}
        raise PublisherError("fail")

    with patch("publisher.run.post_video_to_inbox", side_effect=side_effect):
        processed = run(db_path=tmp_db_path, dry_run=False, mode="inbox")

    assert processed == 1
