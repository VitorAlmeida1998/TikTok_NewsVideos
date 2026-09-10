"""Testes das telas de publicação e de vozes (client de teste, sem rede/custo).

As configurações são redirecionadas pra um arquivo temporário: sem isso os
testes sobrescreveriam o data/settings.json real do usuário.
"""
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from shared.db import get_connection, mark_relevance, save_item, save_script, save_video
from shared.models import NewsItem
from shared.settings import load_settings, save_settings
from webapp.app import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_news.db")
    monkeypatch.setenv("DB_PATH", db_path)

    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("webapp.app.load_settings", lambda: load_settings(settings_path))
    monkeypatch.setattr("webapp.app.save_settings", lambda values: save_settings(values, settings_path))
    monkeypatch.setattr("webapp.app.VOICE_SAMPLES_DIR", tmp_path / "voice_samples")

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        c.settings_path = settings_path
        c.db_path = db_path
        yield c


def make_ready_video(db_path, title="Jogo X leaked", video_path="/tmp/v.mp4", score=5.0, description="Legenda #fyp #games"):
    """Item completo até o vídeo pronto — o estado que entra na fila."""
    with get_connection(db_path) as conn:
        item = NewsItem(title=title, source="ign", url=f"https://e.com/{title}", published_at=None, summary="")
        save_item(conn, item)
        row_id = conn.execute(
            "SELECT id FROM news_items WHERE content_hash = ?", (item.content_hash,)
        ).fetchone()[0]
        mark_relevance(conn, row_id, True, ["leak"], score=score)
        save_script(
            conn, row_id, hook="Hook curto", body="Corpo", cta="Comenta aí!",
            model="m", game_name="Jogo X", description=description,
        )
        save_video(conn, row_id, audio_path="/a.mp3", video_spec_path="/s.json", video_path=video_path)
    return row_id


# --- Fila de publicação ----------------------------------------------------


def test_publish_page_empty(client):
    resp = client.get("/publicar")
    assert resp.status_code == 200
    assert "Nenhum vídeo esperando publicação".encode() in resp.data


def test_publish_page_lists_ready_video_with_caption(client):
    make_ready_video(client.db_path)
    resp = client.get("/publicar")
    assert resp.status_code == 200
    assert b"Jogo X leaked" in resp.data
    assert "Legenda #fyp #games".encode() in resp.data


def test_publish_page_marks_hot_fresh_news_as_post_now(client):
    make_ready_video(client.db_path, title="GTA 6 leaked agora", score=40.0)
    resp = client.get("/publicar")
    assert b"POSTAR AGORA" in resp.data


def test_recalc_schedule_assigns_times(client):
    item_id = make_ready_video(client.db_path, score=2.0)
    resp = client.post("/publicar/recalcular")
    assert resp.status_code == 302

    with get_connection(client.db_path) as conn:
        scheduled = conn.execute(
            "SELECT publish_scheduled_at FROM news_items WHERE id = ?", (item_id,)
        ).fetchone()[0]
    assert scheduled  # ganhou horário de pico


def test_save_publish_settings_persists(client):
    resp = client.post(
        "/publicar/config",
        data={"peak_slots": "11:00, 20:00", "posts_per_day": "2", "min_gap_minutes": "180"},
    )
    assert resp.status_code == 302

    saved = json.loads(client.settings_path.read_text())
    assert saved["peak_slots"] == ["11:00", "20:00"]
    assert saved["posts_per_day"] == 2
    assert saved["min_gap_minutes"] == 180


def test_mark_and_unmark_posted(client):
    item_id = make_ready_video(client.db_path)

    client.post(f"/item/{item_id}/postado", data={"posted": "1"})
    with get_connection(client.db_path) as conn:
        assert conn.execute("SELECT posted_at FROM news_items WHERE id = ?", (item_id,)).fetchone()[0]

    # some da fila e aparece na lista de postados
    resp = client.get("/publicar")
    assert b"Nenhum v\xc3\xaddeo esperando" in resp.data
    assert "Já postados".encode() in resp.data

    client.post(f"/item/{item_id}/postado", data={"posted": "0"})
    with get_connection(client.db_path) as conn:
        assert conn.execute("SELECT posted_at FROM news_items WHERE id = ?", (item_id,)).fetchone()[0] is None


# --- Mídia -----------------------------------------------------------------


def test_media_cover_404_when_missing(client):
    item_id = make_ready_video(client.db_path)
    assert client.get(f"/media/cover/{item_id}").status_code == 404


def test_media_video_download_sets_attachment(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake mp4")
    item_id = make_ready_video(client.db_path, video_path=str(video))

    inline = client.get(f"/media/video/{item_id}")
    assert "attachment" not in inline.headers.get("Content-Disposition", "")

    download = client.get(f"/media/video/{item_id}?download=1")
    assert download.status_code == 200
    assert "attachment" in download.headers["Content-Disposition"]
    assert f"item_{item_id}.mp4" in download.headers["Content-Disposition"]


# --- Vozes -----------------------------------------------------------------


def test_voices_page_lists_candidates(client):
    resp = client.get("/vozes")
    assert resp.status_code == 200
    assert b"pNInz6obpgDQGcFmaJgB" in resp.data  # Adam, voz atual
    assert "Voice ID".encode() in resp.data


def test_voice_sample_rejects_invalid_id(client):
    resp = client.post("/vozes/amostra", data={"voice_id": "../../etc/passwd"})
    assert resp.status_code == 400
    assert "inválido" in resp.get_json()["error"]


def test_voice_sample_rejects_empty_body(client):
    assert client.post("/vozes/amostra").status_code == 400


def test_voice_sample_starts_job_and_writes_file(client, tmp_path):
    """A síntese é mockada: gerar amostra de verdade gasta créditos."""
    sample_dir = tmp_path / "voice_samples"

    def fake_synthesize(text, output_path, voice_id=None, **kwargs):
        from pathlib import Path

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"fake mp3")
        return MagicMock(audio_path=Path(output_path))

    with patch("webapp.app.synthesize_speech", side_effect=fake_synthesize) as mocked:
        resp = client.post("/vozes/amostra", data={"voice_id": "pNInz6obpgDQGcFmaJgB"})
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]

        for _ in range(50):  # o job roda numa thread
            if client.get(f"/api/jobs/{job_id}").get_json()["status"] != "running":
                break
            time.sleep(0.05)

    assert client.get(f"/api/jobs/{job_id}").get_json()["status"] == "done"
    assert mocked.call_args.kwargs["voice_id"] == "pNInz6obpgDQGcFmaJgB"
    assert (sample_dir / "pNInz6obpgDQGcFmaJgB.mp3").exists()

    # e passa a ser servida
    assert client.get("/media/voice-sample/pNInz6obpgDQGcFmaJgB").status_code == 200


def test_use_voice_saves_choice(client):
    resp = client.post(
        "/vozes/usar", data={"voice_id": "XB0fDUnXU5powFXDhCwa", "voice_label": "Voz BR"}
    )
    assert resp.status_code == 302

    saved = json.loads(client.settings_path.read_text())
    assert saved["voice_id"] == "XB0fDUnXU5powFXDhCwa"
    assert saved["voice_label"] == "Voz BR"

    # a voz escolhida aparece como "em uso" na página
    assert b"em uso" in client.get("/vozes").data


def test_use_voice_rejects_invalid_id(client):
    assert client.post("/vozes/usar", data={"voice_id": "nao@vale"}).status_code == 400


def test_media_voice_sample_404_for_unknown(client):
    assert client.get("/media/voice-sample/AAAAAAAAAAAA").status_code == 404


# --- Checklist de SEO na página do item ------------------------------------


def test_item_page_shows_seo_checklist(client):
    item_id = make_ready_video(client.db_path, description="Texto sem hashtag nenhuma")
    resp = client.get(f"/item/{item_id}")
    assert resp.status_code == 200
    assert "Checklist de SEO".encode() in resp.data
    assert "Tem hashtag em português".encode() in resp.data


def test_brand_settings_are_saved_and_normalized(client, tmp_path, monkeypatch):
    import shared.settings as settings_module
    import webapp.app as app_module

    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", path)
    monkeypatch.setattr(app_module, "save_settings", lambda values: settings_module.save_settings(values, path))

    resp = client.post(
        "/marca", data={"channel_handle": "  Fatos de Games  ", "channel_initials": "fg"}
    )
    assert resp.status_code == 302

    saved = settings_module.load_settings(path)
    assert saved["channel_handle"] == "Fatos de Games"
    assert saved["channel_initials"] == "FG"
