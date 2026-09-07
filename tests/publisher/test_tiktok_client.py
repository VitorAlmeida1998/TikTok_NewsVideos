"""Testes do cliente TikTok (mock de requests.Session, sem chamadas reais)."""
from unittest.mock import MagicMock

import pytest

from publisher.tiktok_client import (
    PublisherError,
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
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"data")

    with pytest.raises(PublisherError):
        post_video_to_inbox(video_path)
