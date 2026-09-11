"""Testes da agenda de publicação (horários de pico + notícia quente)."""
from datetime import datetime, timedelta

from publisher.schedule import BR_TZ, build_schedule, parse_slots, upcoming_slots
from shared.settings import DEFAULTS


def _settings(**overrides):
    return {**DEFAULTS, **overrides}


def test_parse_slots_sorts_and_ignores_invalid():
    assert parse_slots(["21:15", "12:15", "nope", "25:99"]) == parse_slots(["12:15", "21:15"])


def test_upcoming_slots_skips_times_already_past_today():
    now = datetime(2026, 9, 9, 19, 0, tzinfo=BR_TZ)
    slots = parse_slots(["12:15", "18:45", "21:15"])
    times = upcoming_slots(now, slots, count=2, posts_per_day=3, min_gap_minutes=150)
    assert times[0] == datetime(2026, 9, 9, 21, 15, tzinfo=BR_TZ)
    assert times[1] == datetime(2026, 9, 10, 12, 15, tzinfo=BR_TZ)


def test_upcoming_slots_respects_posts_per_day():
    now = datetime(2026, 9, 9, 6, 0, tzinfo=BR_TZ)
    slots = parse_slots(["12:15", "18:45", "21:15"])
    times = upcoming_slots(now, slots, count=4, posts_per_day=2, min_gap_minutes=60)
    assert len([t for t in times if t.date() == now.date()]) == 2


def test_upcoming_slots_respects_minimum_gap():
    now = datetime(2026, 9, 9, 6, 0, tzinfo=BR_TZ)
    slots = parse_slots(["12:00", "12:30", "20:00"])
    times = upcoming_slots(now, slots, count=3, posts_per_day=5, min_gap_minutes=120)
    assert datetime(2026, 9, 9, 12, 30, tzinfo=BR_TZ) not in times


def test_hot_fresh_item_is_posted_now_instead_of_waiting():
    now = datetime(2026, 9, 9, 15, 0, tzinfo=BR_TZ)
    items = [{"id": 1, "effective_score": 30.0, "age_hours": 0.5}]
    (post,) = build_schedule(items, now, _settings())
    assert post.post_now is True
    assert "quente" in post.reason


def test_hot_but_old_item_waits_for_a_peak_slot():
    now = datetime(2026, 9, 9, 15, 0, tzinfo=BR_TZ)
    items = [{"id": 1, "effective_score": 30.0, "age_hours": 20.0}]
    (post,) = build_schedule(items, now, _settings())
    assert post.post_now is False
    assert post.when == datetime(2026, 9, 9, 18, 45, tzinfo=BR_TZ)


def test_schedule_spreads_items_and_keeps_existing_times():
    now = datetime(2026, 9, 9, 8, 0, tzinfo=BR_TZ)
    fixed = datetime(2026, 9, 9, 12, 15, tzinfo=BR_TZ)
    items = [
        {"id": 1, "effective_score": 5.0, "age_hours": 10.0, "publish_scheduled_at": fixed.isoformat()},
        {"id": 2, "effective_score": 5.0, "age_hours": 10.0},
        {"id": 3, "effective_score": 5.0, "age_hours": 10.0},
    ]
    posts = {p.item_id: p for p in build_schedule(items, now, _settings())}

    assert posts[1].when == fixed
    # o horário já ocupado não é reaproveitado, e os demais respeitam o intervalo
    others = sorted(p.when for p in (posts[2], posts[3]))
    assert fixed not in others
    assert others[1] - others[0] >= timedelta(minutes=DEFAULTS["min_gap_minutes"])


def test_old_news_is_flagged_stale_instead_of_taking_a_peak_slot():
    now = datetime(2026, 9, 9, 8, 0, tzinfo=BR_TZ)
    items = [
        {"id": 1, "effective_score": 4.0, "age_hours": 70.0},
        {"id": 2, "effective_score": 4.0, "age_hours": 5.0},
    ]
    posts = {p.item_id: p for p in build_schedule(items, now, _settings())}

    assert posts[1].stale is True
    assert posts[1].when is None
    assert posts[1].post_now is False  # não é "postar agora", é "passou o ponto"
    assert "passou o ponto" in posts[1].reason
    # o horário livre foi pro vídeo que ainda vale
    assert posts[2].when == datetime(2026, 9, 9, 12, 15, tzinfo=BR_TZ)


def test_hot_news_is_not_marked_stale():
    now = datetime(2026, 9, 9, 8, 0, tzinfo=BR_TZ)
    (post,) = build_schedule([{"id": 1, "effective_score": 30.0, "age_hours": 1.0}], now, _settings())
    assert post.stale is False
    assert post.post_now is True


def test_only_one_video_per_story_gets_a_slot():
    now = datetime(2026, 9, 9, 8, 0, tzinfo=BR_TZ)
    items = [
        {"id": 10, "effective_score": 9.0, "age_hours": 5.0, "story_group": 10},
        {"id": 11, "effective_score": 8.0, "age_hours": 5.0, "story_group": 10},
        {"id": 12, "effective_score": 7.0, "age_hours": 5.0, "story_group": 12},
    ]
    posts = {p.item_id: p for p in build_schedule(items, now, _settings())}

    assert posts[10].when is not None
    assert posts[11].duplicate is True and posts[11].when is None
    assert posts[11].post_now is False
    assert "#10" in posts[11].reason
    assert posts[12].when is not None  # história diferente segue na fila


def test_items_without_story_group_are_not_treated_as_duplicates():
    now = datetime(2026, 9, 9, 8, 0, tzinfo=BR_TZ)
    items = [
        {"id": 1, "effective_score": 9.0, "age_hours": 5.0, "story_group": None},
        {"id": 2, "effective_score": 8.0, "age_hours": 5.0, "story_group": None},
    ]
    posts = {p.item_id: p for p in build_schedule(items, now, _settings())}
    assert all(p.when is not None for p in posts.values())
