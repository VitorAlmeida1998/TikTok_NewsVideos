"""Testes de carregamento de feeds.yaml."""
import pytest

from collector.feeds_config import FeedConfig, load_feeds


def test_load_feeds_parses_valid_yaml(tmp_path):
    yaml_content = """
feeds:
  - name: ign
    url: https://example.com/ign.xml
  - name: kotaku
    url: https://example.com/kotaku.xml
"""
    feeds_file = tmp_path / "feeds.yaml"
    feeds_file.write_text(yaml_content, encoding="utf-8")

    feeds = load_feeds(feeds_file)

    assert feeds == [
        FeedConfig(name="ign", url="https://example.com/ign.xml"),
        FeedConfig(name="kotaku", url="https://example.com/kotaku.xml"),
    ]


def test_load_feeds_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError):
        load_feeds(missing)


def test_load_feeds_invalid_entry_raises(tmp_path):
    yaml_content = """
feeds:
  - name: ign
"""
    feeds_file = tmp_path / "feeds.yaml"
    feeds_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(ValueError):
        load_feeds(feeds_file)


def test_load_feeds_empty_list(tmp_path):
    feeds_file = tmp_path / "feeds.yaml"
    feeds_file.write_text("feeds: []\n", encoding="utf-8")

    assert load_feeds(feeds_file) == []
