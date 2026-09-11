"""Testes do orquestrador end-to-end (mock de cada etapa, sem custo/rede real)."""
from unittest.mock import patch

from pipeline.run import run_pipeline


def test_run_pipeline_calls_all_steps_in_order():
    call_order = []

    with (
        patch("pipeline.run.collector_run.run", side_effect=lambda **kw: call_order.append("collector") or 5) as m1,
        patch("pipeline.run.dedupe_run.run", side_effect=lambda **kw: call_order.append("dedupe") or (5, 2)) as m2,
        patch("pipeline.run.script_gen_run.run", side_effect=lambda **kw: call_order.append("script_gen") or 2) as m3,
        patch("pipeline.run.video_gen_run.run", side_effect=lambda **kw: call_order.append("video_gen") or 2) as m4,
        patch("pipeline.run.publisher_run.run", side_effect=lambda **kw: call_order.append("publisher") or 2) as m5,
    ):
        summary = run_pipeline(db_path="fake.db")

    assert call_order == ["collector", "dedupe", "script_gen", "video_gen", "publisher"]
    assert summary == {
        "collected": 5,
        "evaluated": 5,
        "relevant": 2,
        "scripted": 2,
        "videos": 2,
        "published": 2,
    }
    m1.assert_called_once()
    m2.assert_called_once()
    m3.assert_called_once()
    m4.assert_called_once()
    m5.assert_called_once()


def test_run_pipeline_defaults_to_publish_dry_run():
    captured = {}

    def fake_publisher_run(**kwargs):
        captured.update(kwargs)
        return 0

    with (
        patch("pipeline.run.collector_run.run", return_value=0),
        patch("pipeline.run.dedupe_run.run", return_value=(0, 0)),
        patch("pipeline.run.script_gen_run.run", return_value=0),
        patch("pipeline.run.video_gen_run.run", return_value=0),
        patch("pipeline.run.publisher_run.run", side_effect=fake_publisher_run),
    ):
        run_pipeline(db_path="fake.db")

    assert captured["dry_run"] is True


def test_run_pipeline_passes_limit_to_relevant_steps():
    captured = {}

    def fake_script_gen_run(**kwargs):
        captured["script_gen_limit"] = kwargs.get("limit")
        return 0

    with (
        patch("pipeline.run.collector_run.run", return_value=0),
        patch("pipeline.run.dedupe_run.run", return_value=(0, 0)),
        patch("pipeline.run.script_gen_run.run", side_effect=fake_script_gen_run),
        patch("pipeline.run.video_gen_run.run", return_value=0),
        patch("pipeline.run.publisher_run.run", return_value=0),
    ):
        run_pipeline(db_path="fake.db", limit=3)

    assert captured["script_gen_limit"] == 3
