"""Testes do orquestrador collector/run.py, sem acesso real à rede
(fetch_feed é mockado para simular a resposta de um feed).
"""
from unittest.mock import patch

from collector.parser import FeedResult
from collector.run import run
from shared.db import get_connection
from shared.models import NewsItem


def _fake_items_for(feed_name: str) -> list[NewsItem]:
    return [
        NewsItem(
            title=f"News from {feed_name}",
            source=feed_name,
            url=f"https://example.com/{feed_name}/1",
            published_at=None,
            summary="summary",
        )
    ]


def _fake_fetch(url, source_name, etag=None, modified=None):
    return FeedResult(
        items=_fake_items_for(source_name), status=200, etag=f"etag-{source_name}", modified=None
    )


def _write_feeds(tmp_path, *names) -> str:
    lines = ["feeds:"]
    for name in names:
        lines += [f"  - name: {name}", f"    url: https://example.com/{name}.xml"]
    path = tmp_path / "feeds.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_run_saves_items_from_all_feeds(tmp_path, tmp_db_path, monkeypatch):
    import collector.run as run_module

    monkeypatch.setattr(run_module, "save_cache", lambda cache: None)
    monkeypatch.setattr(run_module, "load_cache", dict)
    feeds_yaml = _write_feeds(tmp_path, "feed_a", "feed_b")

    with patch("collector.run.fetch_feed", side_effect=_fake_fetch):
        total_new = run(feeds_path=feeds_yaml, db_path=tmp_db_path)

    assert total_new == 2

    with get_connection(tmp_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        assert count == 2


def test_run_continues_when_one_feed_fails(tmp_path, tmp_db_path, monkeypatch):
    import collector.run as run_module

    monkeypatch.setattr(run_module, "save_cache", lambda cache: None)
    monkeypatch.setattr(run_module, "load_cache", dict)
    feeds_yaml = _write_feeds(tmp_path, "good_feed", "bad_feed")

    def side_effect(url, source_name, etag=None, modified=None):
        if source_name == "bad_feed":
            raise ValueError("network error")
        return _fake_fetch(url, source_name)

    with patch("collector.run.fetch_feed", side_effect=side_effect):
        total_new = run(feeds_path=feeds_yaml, db_path=tmp_db_path)

    assert total_new == 1


def test_run_sends_cached_validators_and_skips_unchanged_feeds(tmp_path, tmp_db_path, monkeypatch):
    """GET condicional: o feed que responde 304 não é reprocessado, e o
    ETag guardado é reenviado na próxima rodada."""
    import collector.run as run_module

    saved: dict = {}
    monkeypatch.setattr(run_module, "save_cache", lambda cache: saved.update(cache))
    monkeypatch.setattr(run_module, "load_cache", lambda: dict(saved))
    feeds_yaml = _write_feeds(tmp_path, "feed_a")

    with patch("collector.run.fetch_feed", side_effect=_fake_fetch):
        assert run(feeds_path=feeds_yaml, db_path=tmp_db_path) == 1
    assert saved["https://example.com/feed_a.xml"]["etag"] == "etag-feed_a"

    sent = {}

    def not_modified(url, source_name, etag=None, modified=None):
        sent["etag"] = etag
        return FeedResult(items=[], status=304, etag=etag, modified=modified)

    with patch("collector.run.fetch_feed", side_effect=not_modified):
        assert run(feeds_path=feeds_yaml, db_path=tmp_db_path) == 0

    assert sent["etag"] == "etag-feed_a"  # reenviou o validador guardado
