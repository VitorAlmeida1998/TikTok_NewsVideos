"""Testes das travas que protegem a cota de TTS: teto diário de vídeos e
reserva de caracteres do ElevenLabs."""
from unittest.mock import MagicMock, patch

from shared.db import (
    get_connection,
    mark_relevance,
    save_item,
    save_script,
    save_video,
)
from shared.models import NewsItem
from video_gen.quota import has_budget_for, remaining_characters
from video_gen.run import run


def _client(used: int, limit: int) -> MagicMock:
    client = MagicMock()
    client.user.subscription.get.return_value = MagicMock(
        character_count=used, character_limit=limit
    )
    return client


def test_remaining_characters_reads_subscription():
    assert remaining_characters(_client(9476, 30074)) == 20598


def test_remaining_characters_returns_none_when_api_denies():
    client = MagicMock()
    client.user.subscription.get.side_effect = RuntimeError("missing permission voices_read")
    assert remaining_characters(client) is None


def test_has_budget_respects_reserve():
    client = _client(used=29000, limit=30000)  # restam 1000
    assert has_budget_for(400, reserve=200, client=client) is True
    assert has_budget_for(400, reserve=800, client=client) is False


def test_has_budget_allows_when_quota_unreadable():
    client = MagicMock()
    client.user.subscription.get.side_effect = RuntimeError("sem permissão")
    assert has_budget_for(10_000, reserve=5_000, client=client) is True


def _scripted(conn, title, url):
    item = NewsItem(title=title, source="ign", url=url, published_at=None, summary="")
    save_item(conn, item)
    row_id = conn.execute(
        "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
    ).fetchone()[0]
    mark_relevance(conn, row_id, True, ["leak"], score=5)
    save_script(conn, row_id, hook="Hook", body="Corpo", cta="CTA", model="m", game_name=title)
    return row_id


def _ok_result(row, render=True, require_media=False):
    return {
        "item_id": row["id"],
        "audio_path": "/a.mp3",
        "spec_path": "/s.json",
        "video_path": f"/v{row['id']}.mp4",
    }


def test_daily_limit_counts_videos_from_last_24h(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        for i in range(4):
            _scripted(conn, f"Jogo {i} leaked", f"https://e.com/{i}")

    with patch("video_gen.run.generate_video_for_item", side_effect=_ok_result):
        assert run(db_path=tmp_db_path, daily_limit=2) == 2
        # segunda rodada no mesmo dia não gera mais nada
        assert run(db_path=tmp_db_path, daily_limit=2) == 0


def test_daily_limit_narrows_but_never_widens_per_cycle_limit(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        for i in range(5):
            _scripted(conn, f"Jogo {i} leaked", f"https://e.com/{i}")

    with patch("video_gen.run.generate_video_for_item", side_effect=_ok_result):
        assert run(db_path=tmp_db_path, limit=1, daily_limit=10) == 1


def test_generation_stops_when_tts_budget_is_over(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        for i in range(3):
            _scripted(conn, f"Jogo {i} leaked", f"https://e.com/{i}")

    with (
        patch("video_gen.run.generate_video_for_item", side_effect=_ok_result),
        patch("video_gen.run.has_budget_for", return_value=False) as budget,
    ):
        assert run(db_path=tmp_db_path, tts_reserve_chars=2000) == 0
    budget.assert_called_once()  # para no primeiro item, não tenta os outros


def test_old_videos_do_not_count_towards_daily_limit(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        old_id = _scripted(conn, "Antigo leaked", "https://e.com/old")
        save_video(conn, old_id, audio_path="/a", video_spec_path="/s", video_path="/v.mp4")
        conn.execute(
            "UPDATE news_items SET video_generated_at = '2020-01-01T00:00:00+00:00' WHERE id = ?",
            (old_id,),
        )
        _scripted(conn, "Novo leaked", "https://e.com/new")

    with patch("video_gen.run.generate_video_for_item", side_effect=_ok_result):
        assert run(db_path=tmp_db_path, daily_limit=1) == 1


def test_weak_story_does_not_burn_a_daily_slot(tmp_db_path):
    """A vaga do dia é escassa: notícia abaixo do piso não vira vídeo, pra
    sobrar espaço pra pauta forte que aparecer mais tarde."""
    with get_connection(tmp_db_path) as conn:
        forte = _scripted(conn, "Jogo forte leaked", "https://e.com/forte")
        fraca = _scripted(conn, "Jogo fraco leaked", "https://e.com/fraca")
        conn.execute("UPDATE news_items SET relevance_score = 30 WHERE id = ?", (forte,))
        conn.execute("UPDATE news_items SET relevance_score = 5 WHERE id = ?", (fraca,))

    with patch("video_gen.run.generate_video_for_item", side_effect=_ok_result) as gen:
        assert run(db_path=tmp_db_path, min_score=12.0) == 1

    assert gen.call_count == 1
    assert gen.call_args[0][0]["id"] == forte


def test_daily_limit_counts_by_calendar_day_not_rolling_window(tmp_db_path):
    """Lote gerado ontem à noite não pode bloquear a manhã de hoje."""
    from datetime import datetime, timedelta, timezone

    with get_connection(tmp_db_path) as conn:
        ontem = _scripted(conn, "Vídeo de ontem leaked", "https://e.com/ontem")
        save_video(conn, ontem, audio_path="/a", video_spec_path="/s", video_path="/v.mp4")
        # 23h atrás, mas no dia anterior no calendário
        anterior = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
        conn.execute("UPDATE news_items SET video_generated_at = ? WHERE id = ?", (anterior, ontem))
        _scripted(conn, "Notícia de hoje leaked", "https://e.com/hoje")

    from publisher.schedule import start_of_day
    from shared.db import count_videos_generated_since

    with get_connection(tmp_db_path) as conn:
        hoje = count_videos_generated_since(conn, since=start_of_day())
        janela = count_videos_generated_since(conn, hours=24)

    assert janela == 1  # a janela deslizante ainda enxerga o vídeo de ontem
    assert hoje <= 1  # a contagem por dia zera na virada
