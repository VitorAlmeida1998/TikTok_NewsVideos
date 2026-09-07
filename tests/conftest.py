"""Fixtures compartilhadas pelos testes."""
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_feed_path() -> Path:
    return FIXTURES_DIR / "sample_feed.xml"


@pytest.fixture
def sample_feed_content(sample_feed_path: Path) -> str:
    return sample_feed_path.read_text(encoding="utf-8")


@pytest.fixture
def tmp_db_path(tmp_path) -> str:
    return str(tmp_path / "test_news.db")
