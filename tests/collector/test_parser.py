"""Testes do parser de feeds (100% offline, via fixture local)."""
from collector.parser import parse_feed
from shared.models import NewsItem


def test_parse_feed_returns_all_items(sample_feed_content):
    items = parse_feed(sample_feed_content, source_name="sample")
    assert len(items) == 3


def test_parse_feed_normalizes_fields(sample_feed_content):
    items = parse_feed(sample_feed_content, source_name="sample")
    first = items[0]

    assert isinstance(first, NewsItem)
    assert first.title == "Big Sequel Leaked Ahead of Official Reveal"
    assert first.source == "sample"
    assert first.url == "https://example.com/news/big-sequel-leaked"
    assert first.summary
    assert first.published_at is not None
    assert first.published_at.year == 2025
    assert first.published_at.month == 9
    assert first.published_at.day == 1


def test_parse_feed_skips_entries_without_title_or_link():
    broken_feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
        <item><title>No link here</title></item>
        <item><link>https://example.com/no-title</link></item>
    </channel></rss>
    """
    items = parse_feed(broken_feed, source_name="broken")
    assert items == []


def test_parse_feed_empty_feed_returns_empty_list():
    empty_feed = """<?xml version="1.0"?>
    <rss version="2.0"><channel></channel></rss>
    """
    items = parse_feed(empty_feed, source_name="empty")
    assert items == []
