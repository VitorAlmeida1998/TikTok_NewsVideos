"""Testes do cliente TikTok (mock de requests.Session, sem chamadas reais)."""
import time
from unittest.mock import MagicMock

import pytest

import publisher.tiktok_client as tiktok_client
from publisher.tiktok_client import (
    PublisherError,
    _get_access_token,
    check_publish_status,
    post_video_direct,
    post_video_to_inbox,
)


def _make_session(init_json: dict, put_status: int = 200, status_json: dict | None = None):
    session = MagicMock()

    init_resp = MagicMock()
    init_resp.status_code = 200
    init_resp.json.return_value = init_json
    session.post.return_value = init_resp

    put_resp = MagicMock()
    put_resp.status_code = put_status
    session.put.return_value = put_resp

    if status_json is not None:
        status_resp = MagicMock()
        status_resp.status_code = 200
        status_resp.json.return_value = status_json
        session.post.side_effect = [init_resp, status_resp]

    return session


def test_post_video_to_inbox_success(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video bytes")

    init_json = {"data": {"publish_id": "pub123", "upload_url": "https://upload.example/x"}}
    session = _make_session(init_json)

    result = post_video_to_inbox(video_path, access_token="tok", session=session)

    assert result == init_json
    session.post.assert_called_once()
    session.put.assert_called_once()
    put_kwargs = session.put.call_args
    assert put_kwargs.args[0] == "https://upload.example/x"


def test_post_video_to_inbox_raises_if_file_missing(tmp_path):
    missing = tmp_path / "does_not_exist.mp4"
    with pytest.raises(PublisherError):
        post_video_to_inbox(missing, access_token="tok", session=MagicMock())


def test_post_video_to_inbox_raises_on_bad_status(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"data")

    session = MagicMock()
    bad_resp = MagicMock()
    bad_resp.status_code = 401
    bad_resp.text = "unauthorized"
    session.post.return_value = bad_resp

    with pytest.raises(PublisherError):
        post_video_to_inbox(video_path, access_token="bad-tok", session=session)


def test_post_video_direct_sends_post_info(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video bytes")

    init_json = {"data": {"publish_id": "pub456", "upload_url": "https://upload.example/y"}}
    session = _make_session(init_json)

    result = post_video_direct(
        video_path, title="Meu vídeo", access_token="tok", session=session
    )

    assert result == init_json
    call_kwargs = session.post.call_args
    sent_body = call_kwargs.kwargs["json"]
    assert sent_body["post_info"]["title"] == "Meu vídeo"
    assert sent_body["post_info"]["privacy_level"] == "SELF_ONLY"


def test_check_publish_status_returns_json():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": {"status": "PUBLISH_COMPLETE"}}
    session.post.return_value = resp

    result = check_publish_status("pub123", access_token="tok", session=session)
    assert result["data"]["status"] == "PUBLISH_COMPLETE"


def test_missing_access_token_raises_publisher_error(tmp_path, monkeypatch):
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(tiktok_client, "load_tokens", lambda: None)
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"data")

    with pytest.raises(PublisherError):
        post_video_to_inbox(video_path)


def test_get_access_token_uses_valid_stored_token(monkeypatch):
    monkeypatch.setattr(
        tiktok_client, "load_tokens", lambda: {"access_token": "stored-at", "expires_at": time.time() + 3600}
    )
    assert _get_access_token() == "stored-at"


def test_get_access_token_refreshes_when_expired(monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        tiktok_client,
        "load_tokens",
        lambda: {"access_token": "old-at", "refresh_token": "old-rt", "expires_at": time.time() - 10},
    )
    monkeypatch.setattr(
        tiktok_client,
        "refresh_access_token",
        lambda refresh_token, client_key, client_secret: {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 86400,
        },
    )
    saved = {}
    monkeypatch.setattr(
        tiktok_client,
        "save_tokens",
        lambda access_token, refresh_token, expires_in: saved.update(
            access_token=access_token, refresh_token=refresh_token
        ),
    )

    assert _get_access_token() == "new-at"
    assert saved == {"access_token": "new-at", "refresh_token": "new-rt"}


def test_get_access_token_falls_back_to_env_when_no_refresh_possible(monkeypatch):
    monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
    monkeypatch.delenv("TIKTOK_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "manual-token")
    monkeypatch.setattr(tiktok_client, "load_tokens", lambda: None)

    assert _get_access_token() == "manual-token"
