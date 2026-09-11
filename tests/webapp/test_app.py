"""Testes básicos da webapp Flask (client de teste, sem subir servidor real)."""
import sqlite3
from datetime import datetime, timezone

import pytest

from shared.db import get_connection, save_item
from shared.models import NewsItem
from webapp.app import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_news.db")
    monkeypatch.setenv("DB_PATH", db_path)

    # popula um item de teste
    with get_connection(db_path) as conn:
        item = NewsItem(
            title="Teste: Novo jogo revelado",
            source="testsource",
            url="https://example.com/teste",
            published_at=None,
            summary="Um resumo de teste.",
        )
        save_item(conn, item)
        conn.execute(
            "UPDATE news_items SET is_relevant = 1 WHERE title = ?", (item.title,)
        )

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_index_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"TikTok GameNews" in resp.data


def test_index_filters_by_status(client):
    resp = client.get("/?status=relevant")
    assert resp.status_code == 200
    assert b"Teste: Novo jogo revelado" in resp.data


def test_index_search(client):
    resp = client.get("/?q=Novo jogo")
    assert resp.status_code == 200
    assert b"Teste: Novo jogo revelado" in resp.data

    resp_empty = client.get("/?q=inexistente-xyz")
    assert b"Teste: Novo jogo revelado" not in resp_empty.data


def test_item_detail_loads(client):
    resp = client.get("/item/1")
    assert resp.status_code == 200
    assert b"Teste: Novo jogo revelado" in resp.data


def test_item_detail_404_for_missing(client):
    resp = client.get("/item/99999")
    assert resp.status_code == 404


def test_save_script_persists(client):
    resp = client.post(
        "/item/1/script",
        data={
            "game_name": "Jogo Teste",
            "hook": "Hook de teste",
            "body": "Corpo de teste",
            "cta": "CTA de teste",
        },
    )
    assert resp.status_code == 302

    detail = client.get("/item/1")
    assert b"Hook de teste" in detail.data
    assert b"Jogo Teste" in detail.data


def test_jobs_page_loads(client):
    resp = client.get("/jobs")
    assert resp.status_code == 200


def test_api_job_status_not_found(client):
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_media_video_404_when_missing(client):
    resp = client.get("/media/video/1")
    assert resp.status_code == 404


def test_media_background_404_when_missing(client):
    resp = client.get("/media/background/nonexistent-slug")
    assert resp.status_code == 404
