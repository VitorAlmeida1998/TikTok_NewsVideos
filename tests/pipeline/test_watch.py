"""Testes do monitor contínuo (mock de cada etapa, sem rede/custo)."""
import json
from unittest.mock import patch

from pipeline.watch import read_status, run_cycle, watch_forever


def _patches(collected=0, videos=0):
    return (
        patch("pipeline.watch.collector_run.run", return_value=collected),
        patch("pipeline.watch.dedupe_run.run", return_value=(collected, 1)),
        patch("pipeline.watch.script_gen_run.run", return_value=1),
        patch("pipeline.watch.video_gen_run.run", return_value=videos),
        patch("pipeline.watch.refresh_publish_schedule", return_value=0),
    )


def test_run_cycle_chains_all_steps_with_autonomous_flags():
    captured = {}

    def fake_video(**kwargs):
        captured.update(kwargs)
        return 2

    with (
        patch("pipeline.watch.collector_run.run", return_value=3),
        patch("pipeline.watch.dedupe_run.run", return_value=(3, 2)),
        patch("pipeline.watch.script_gen_run.run", return_value=2),
        patch("pipeline.watch.video_gen_run.run", side_effect=fake_video),
        patch("pipeline.watch.refresh_publish_schedule", return_value=2),
    ):
        summary = run_cycle(db_path="x.db", limit=3, require_media=True, max_age_hours=48)

    assert summary == {
        "collected": 3, "evaluated": 3, "relevant": 2, "scripted": 2, "videos": 2, "scheduled": 2,
    }
    assert captured["require_media"] is True
    assert captured["max_age_hours"] == 48
    assert captured["limit"] == 3


def test_watch_once_writes_status_file_readable_by_dashboard(tmp_path):
    status_path = tmp_path / "status.json"
    p1, p2, p3, p4, p5 = _patches(collected=5, videos=1)
    with p1, p2, p3, p4, p5:
        watch_forever(interval_seconds=120, once=True, status_path=status_path, db_path="x.db")

    raw = json.loads(status_path.read_text())
    assert raw["collected"] == 5 and raw["videos"] == 1
    status = read_status(status_path)
    assert status["alive"] is True
    assert status["seconds_since_check"] >= 0


def test_watch_survives_a_failing_cycle(tmp_path):
    status_path = tmp_path / "status.json"
    with patch("pipeline.watch.collector_run.run", side_effect=RuntimeError("feed down")):
        watch_forever(interval_seconds=120, once=True, status_path=status_path)
    assert json.loads(status_path.read_text())["error"] is True


def test_read_status_missing_or_stale(tmp_path):
    assert read_status(tmp_path / "nope.json") is None
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps({"last_check": "2020-01-01T00:00:00+00:00", "interval_seconds": 120}))
    assert read_status(stale)["alive"] is False


def test_cycle_schedules_ready_videos_for_peak_hours(tmp_db_path):
    from shared.db import get_connection, get_publish_queue, mark_relevance, save_item, save_script, save_video
    from shared.models import NewsItem
    from pipeline.watch import refresh_publish_schedule

    with get_connection(tmp_db_path) as conn:
        for i in range(2):
            item = NewsItem(
                title=f"Jogo {i} leaked", source="ign", url=f"https://e.com/{i}", published_at=None, summary=""
            )
            save_item(conn, item)
            row_id = conn.execute(
                "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
            ).fetchone()[0]
            mark_relevance(conn, row_id, True, ["leak"], score=5)
            save_script(conn, row_id, hook="h", body="b", cta="c", model="m", game_name="Jogo")
            save_video(conn, row_id, audio_path="/a", video_spec_path="/s", video_path=f"/v{i}.mp4")

    assert refresh_publish_schedule(db_path=tmp_db_path) == 2

    with get_connection(tmp_db_path) as conn:
        times = [row["publish_scheduled_at"] for row in get_publish_queue(conn)]
        assert all(times), "todo vídeo pronto deve sair da rodada com horário"
        # rodar de novo não remexe no que já foi agendado
        assert refresh_publish_schedule(db_path=tmp_db_path) == 0


def test_schedule_handles_stale_items_without_crashing(tmp_db_path):
    """Regressão: item "passou o ponto" tem when=None e post_now=False — o log
    do monitor não pode assumir que sempre há datetime."""
    from datetime import datetime, timedelta, timezone

    from shared.db import get_connection, mark_relevance, save_item, save_script, save_video
    from shared.models import NewsItem
    from pipeline.watch import refresh_publish_schedule

    with get_connection(tmp_db_path) as conn:
        item = NewsItem(
            title="Notícia velha leaked",
            source="ign",
            url="https://e.com/velha",
            published_at=None,
            summary="",
            collected_at=datetime.now(timezone.utc) - timedelta(hours=100),
        )
        save_item(conn, item)
        row_id = conn.execute(
            "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
        ).fetchone()[0]
        mark_relevance(conn, row_id, True, ["leak"], score=5)
        save_script(conn, row_id, hook="h", body="b", cta="c", model="m", game_name="Jogo")
        save_video(conn, row_id, audio_path="/a", video_spec_path="/s", video_path="/v.mp4")

    assert refresh_publish_schedule(db_path=tmp_db_path) == 1
    with get_connection(tmp_db_path) as conn:
        assert conn.execute(
            "SELECT publish_scheduled_at FROM news_items WHERE id = ?", (row_id,)
        ).fetchone()[0] is None
