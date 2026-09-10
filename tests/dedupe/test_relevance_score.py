"""Testes da pontuação de relevância (ordem de prioridade do modo autônomo)."""
from dedupe.keyword_filter import relevance_score
from dedupe.run import run
from shared.db import get_connection, get_items_pending_script, save_item
from shared.models import NewsItem


def test_score_is_zero_without_keywords():
    assert relevance_score("A quiet day", "nothing here", "ign") == 0.0


def test_leak_scores_higher_than_trailer():
    leak = relevance_score("Big Game leaked", "", "ign")
    trailer = relevance_score("Big Game trailer", "", "ign")
    assert leak > trailer > 0


def test_keyword_in_title_beats_keyword_only_in_summary():
    in_title = relevance_score("Sequel delayed", "", "ign")
    in_summary = relevance_score("Sequel news", "it was delayed", "ign")
    assert in_title > in_summary


def test_hype_terms_and_source_weight_apply():
    plain = relevance_score("Indie game revealed", "", "pcgamer")
    hyped = relevance_score("GTA 6 revealed", "", "pcgamer")
    b2b = relevance_score("GTA 6 revealed", "", "gamesindustry")
    assert hyped > plain
    assert b2b < hyped


def test_dedupe_run_stores_score_and_pending_queue_is_ordered_by_it(tmp_db_path):
    def make(title, url):
        return NewsItem(title=title, source="ign", url=url, published_at=None, summary="")

    with get_connection(tmp_db_path) as conn:
        save_item(conn, make("Small studio trailer", "https://e.com/1"))
        save_item(conn, make("GTA 6 release date leaked", "https://e.com/2"))
        save_item(conn, make("Nothing relevant here", "https://e.com/3"))

    run(db_path=tmp_db_path)

    with get_connection(tmp_db_path) as conn:
        pending = get_items_pending_script(conn)
        assert [r["title"] for r in pending] == [
            "GTA 6 release date leaked",
            "Small studio trailer",
        ]
        assert pending[0]["relevance_score"] > pending[1]["relevance_score"] > 0


def test_pending_script_respects_max_age(tmp_db_path):
    from datetime import datetime, timedelta, timezone

    old = NewsItem(
        title="Old game leaked",
        source="ign",
        url="https://e.com/old",
        published_at=None,
        summary="",
        collected_at=datetime.now(timezone.utc) - timedelta(hours=100),
    )
    new = NewsItem(
        title="New game leaked", source="ign", url="https://e.com/new", published_at=None, summary=""
    )
    with get_connection(tmp_db_path) as conn:
        save_item(conn, old)
        save_item(conn, new)
    run(db_path=tmp_db_path)

    with get_connection(tmp_db_path) as conn:
        assert len(get_items_pending_script(conn)) == 2
        recent = get_items_pending_script(conn, max_age_hours=48)
        assert [r["title"] for r in recent] == ["New game leaked"]


def test_freshness_multiplier_decays_with_age():
    from dedupe.keyword_filter import FRESHNESS_FLOOR, freshness_multiplier

    assert freshness_multiplier(0) == 1.0
    assert freshness_multiplier(24) < freshness_multiplier(1)
    assert freshness_multiplier(1000) == FRESHNESS_FLOOR


def test_pending_queue_prefers_fresh_news_over_slightly_stronger_old_news(tmp_db_path):
    from datetime import datetime, timedelta, timezone

    from shared.db import get_connection, get_items_pending_script, save_item
    from shared.models import NewsItem
    from dedupe.run import run

    old = NewsItem(
        title="Old game leaked",
        source="ign",
        url="https://e.com/old",
        published_at=None,
        summary="",
        collected_at=datetime.now(timezone.utc) - timedelta(hours=40),
    )
    fresh = NewsItem(
        title="Fresh game leaked", source="ign", url="https://e.com/fresh", published_at=None, summary=""
    )
    with get_connection(tmp_db_path) as conn:
        save_item(conn, old)
        save_item(conn, fresh)
    run(db_path=tmp_db_path)

    with get_connection(tmp_db_path) as conn:
        # a antiga tem score BASE maior...
        conn.execute("UPDATE news_items SET relevance_score = 20 WHERE title = 'Old game leaked'")
        conn.execute("UPDATE news_items SET relevance_score = 15 WHERE title = 'Fresh game leaked'")
        # ...mas 40h de decaimento (x0.44) a deixam abaixo da fresca (x1.0)
        assert get_items_pending_script(conn)[0]["title"] == "Fresh game leaked"
