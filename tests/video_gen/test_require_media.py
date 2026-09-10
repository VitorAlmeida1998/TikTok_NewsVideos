"""Testes do modo autônomo do video_gen: itens sem fundo/música são pulados
ANTES do TTS e ficam marcados como "aguardando mídia"."""
from pathlib import Path
from unittest.mock import patch

import pytest

from shared.db import (
    get_connection,
    get_status_counts,
    list_items,
    mark_relevance,
    save_item,
    save_script,
)
from shared.models import NewsItem
from video_gen.assembler import MediaMissingError, generate_video_for_item
from video_gen.run import run


def _row(game_name="Some Game"):
    return {
        "id": 7,
        "title": "t",
        "source": "ign",
        "script_hook": "h",
        "script_body": "b",
        "script_cta": "c",
        "game_name": game_name,
        "matched_keywords": "leak",
        "script_pronunciations": "",
    }


class _Row(dict):
    def keys(self):
        return list(super().keys())


def test_require_media_raises_before_tts_when_clip_missing():
    with (
        patch("video_gen.assembler.download_trailer_clip", return_value=None),
        patch("video_gen.assembler.download_ost_clip", return_value=Path("/tmp/x.mp3")),
        patch("video_gen.assembler.synthesize_speech") as tts,
    ):
        with pytest.raises(MediaMissingError, match="vídeo de fundo"):
            generate_video_for_item(_Row(_row()), render=False, require_media=True)
    tts.assert_not_called()


def test_require_media_raises_when_no_game_name():
    with patch("video_gen.assembler.synthesize_speech") as tts:
        with pytest.raises(MediaMissingError, match="sem nome de jogo"):
            generate_video_for_item(_Row(_row(game_name="")), render=False, require_media=True)
    tts.assert_not_called()


def _scripted_item(conn, title, url, game_name="Game"):
    item = NewsItem(title=title, source="ign", url=url, published_at=None, summary="")
    save_item(conn, item)
    row_id = conn.execute(
        "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
    ).fetchone()[0]
    mark_relevance(conn, row_id, True, ["leak"], score=5)
    save_script(conn, row_id, hook="h", body="b", cta="c", model="m", game_name=game_name)
    return row_id


def test_run_marks_skipped_items_as_awaiting_media_and_clears_on_success(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        _scripted_item(conn, "Sem mídia", "https://e.com/a")
        ok_id = _scripted_item(conn, "Com mídia", "https://e.com/b")

    def fake_generate(row, render=True, require_media=False):
        if row["title"] == "Sem mídia":
            raise MediaMissingError("sem música para 'Game'")
        return {"item_id": row["id"], "audio_path": "/a.mp3", "spec_path": "/s.json", "video_path": "/v.mp4"}

    with patch("video_gen.run.generate_video_for_item", side_effect=fake_generate):
        generated = run(db_path=tmp_db_path, require_media=True)

    assert generated == 1
    with get_connection(tmp_db_path) as conn:
        waiting = list_items(conn, status="awaiting_media")
        assert [r["title"] for r in waiting] == ["Sem mídia"]
        assert waiting[0]["video_skip_reason"] == "sem música para 'Game'"
        assert get_status_counts(conn)["awaiting_media"] == 1
        done = conn.execute("SELECT video_skip_reason FROM news_items WHERE id = ?", (ok_id,)).fetchone()
        assert done[0] is None

    # usuário envia a mídia, próxima rodada gera e limpa o motivo
    with patch(
        "video_gen.run.generate_video_for_item",
        return_value={"item_id": 1, "audio_path": "/a", "spec_path": "/s", "video_path": "/v"},
    ):
        run(db_path=tmp_db_path, require_media=True)
    with get_connection(tmp_db_path) as conn:
        assert get_status_counts(conn)["awaiting_media"] == 0


def test_limit_counts_generated_videos_not_skipped_items(tmp_db_path):
    with get_connection(tmp_db_path) as conn:
        for i in range(3):
            _scripted_item(conn, f"Sem mídia {i}", f"https://e.com/skip{i}")
        _scripted_item(conn, "Com mídia", "https://e.com/ok")
        conn.execute("UPDATE news_items SET relevance_score = 1 WHERE title = 'Com mídia'")

    def fake_generate(row, render=True, require_media=False):
        if row["title"].startswith("Sem mídia"):
            raise MediaMissingError("sem música")
        return {"item_id": row["id"], "audio_path": "/a", "spec_path": "/s", "video_path": "/v"}

    with patch("video_gen.run.generate_video_for_item", side_effect=fake_generate):
        assert run(db_path=tmp_db_path, limit=1, require_media=True) == 1
