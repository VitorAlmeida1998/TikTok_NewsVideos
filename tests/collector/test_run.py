"""Testes do orquestrador collector/run.py, sem acesso real à rede
(parse_feed é mockado para simular a resposta de um feed).
"""
from unittest.mock import patch

from collector.run import run
from shared.db import get_connection
from shared.models import NewsItem


def _fake_items_for(feed_url: str, feed_name: str) -> list[NewsItem]:
    return [
        NewsItem(
            title=f"News from {feed_name}",
            source=feed_name,
            url=f"https://example.com/{feed_name}/1",
            published_at=None,
            summary="summary",
        )
    ]


def test_run_saves_items_from_all_feeds(tmp_path, tmp_db_path):
    feeds_yaml = tmp_path / "feeds.yaml"
    feeds_yaml.write_text(
        """
feeds:
  - name: feed_a
    url: https://example.com/a.xml
  - name: feed_b
    url: https://example.com/b.xml
""",
        encoding="utf-8",
    )

    with patch("collector.run.parse_feed", side_effect=_fake_items_for):
        total_new = run(feeds_path=str(feeds_yaml), db_path=tmp_db_path)

    assert total_new == 2

    with get_connection(tmp_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        assert count == 2


def test_run_continues_when_one_feed_fails(tmp_path, tmp_db_path):
    feeds_yaml = tmp_path / "feeds.yaml"
    feeds_yaml.write_text(
        """
feeds:
  - name: good_feed
    url: https://example.com/good.xml
  - name: bad_feed
    url: https://example.com/bad.xml
""",
        encoding="utf-8",
    )

    def side_effect(feed_url, feed_name):
        if feed_name == "bad_feed":
            raise ValueError("network error")
        return _fake_items_for(feed_url, feed_name)

    with patch("collector.run.parse_feed", side_effect=side_effect):
        total_new = run(feeds_path=str(feeds_yaml), db_path=tmp_db_path)

    assert total_new == 1
