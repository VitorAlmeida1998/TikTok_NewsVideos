"""Testes do agrupamento de notícias que contam a mesma história."""
from dedupe.run import run
from dedupe.story_group import find_story_group, similarity, title_tokens
from shared.db import (
    get_connection,
    get_items_pending_script,
    get_items_pending_video,
    mark_relevance,
    save_item,
    save_script,
    save_video,
)
from shared.models import NewsItem


def test_title_tokens_drops_stopwords_but_keeps_numbers_and_short_names():
    tokens = title_tokens("The new GTA 6 trailer is out")
    assert "gta" in tokens and "6" in tokens and "trailer" in tokens
    assert "the" not in tokens and "is" not in tokens


def test_similarity_high_for_same_story_low_for_different():
    a = "Forza Horizon 6 appears to have been quietly delayed on PS5"
    b = "Forza Horizon 6 has not been delayed on PS5, developer confirms"
    c = "Kirby and the World Beyond revealed with gameplay"
    assert similarity(a, b) > 0.45
    assert similarity(a, c) < 0.2


def test_find_story_group_returns_none_for_new_story():
    candidates = [(1, "Kirby revealed at Nintendo Direct", None)]
    assert find_story_group("GTA 6 delayed again", candidates) is None


def test_find_story_group_follows_existing_group_id():
    # item 2 já pertence ao grupo do item 1; o novo item deve cair no grupo 1
    candidates = [(2, "Forza Horizon 6 not delayed on PS5, says studio", 1)]
    title = "Forza Horizon 6 quietly delayed on PS5"
    assert find_story_group(title, candidates) == 1


def _add(conn, title, url):
    item = NewsItem(title=title, source="ign", url=url, published_at=None, summary="")
    save_item(conn, item)
    return conn.execute(
        "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
    ).fetchone()[0]


def test_run_groups_duplicate_coverage_and_queue_offers_only_one(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        first = _add(conn, "Forza Horizon 6 appears to have been delayed on PS5", "https://e.com/1")
        _add(conn, "Forza Horizon 6 has not been delayed on PS5, developer confirms", "https://e.com/2")
        _add(conn, "Kirby and the World Beyond revealed with gameplay trailer", "https://e.com/3")

    run(db_path=tmp_db_path)

    with get_connection(tmp_db_path) as conn:
        groups = dict(conn.execute("SELECT id, story_group FROM news_items").fetchall())
        assert groups[first] == first
        assert len(set(groups.values())) == 2  # Forza (2 itens) + Kirby

        # todos ainda sem roteiro: a fila mostra os dois grupos
        pending = get_items_pending_script(conn)
        assert len(pending) == 3

        # gerado o roteiro do primeiro Forza, o segundo sai da fila
        save_script(conn, first, hook="h", body="b", cta="c", model="m", game_name="Forza Horizon 6")
        titles = [row["title"] for row in get_items_pending_script(conn)]
        assert not any("Forza" in t for t in titles)
        assert any("Kirby" in t for t in titles)


def test_video_queue_skips_story_that_already_has_a_video(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        first = _add(conn, "GTA 6 release date confirmed for next May", "https://e.com/1")
        second = _add(conn, "GTA 6 release date confirmed, Rockstar says next May", "https://e.com/2")
    run(db_path=tmp_db_path)

    with get_connection(tmp_db_path) as conn:
        for item_id in (first, second):
            save_script(conn, item_id, hook="h", body="b", cta="c", model="m", game_name="GTA 6")
        assert len(get_items_pending_video(conn)) == 2

        save_video(conn, first, audio_path="/a", video_spec_path="/s", video_path="/v.mp4")
        remaining = get_items_pending_video(conn)
        assert [r["id"] for r in remaining] == []
