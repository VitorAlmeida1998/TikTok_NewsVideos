"""Testes do fluxo OAuth2 do TikTok (mock de requests.Session, sem chamadas reais)."""
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

from publisher.oauth import (
    OAuthError,
    build_authorize_url,
    exchange_code_for_token,
    refresh_access_token,
)


def test_build_authorize_url_has_required_params():
    url = build_authorize_url("key123", "https://example.com/callback")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert qs["client_key"] == ["key123"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["video.upload"]
    assert qs["redirect_uri"] == ["https://example.com/callback"]
    assert "state" not in qs


def test_build_authorize_url_includes_state_when_given():
    url = build_authorize_url("key123", "https://example.com/callback", state="xyz")
    qs = parse_qs(urlparse(url).query)
    assert qs["state"] == ["xyz"]


def test_build_authorize_url_accepts_custom_scope():
    url = build_authorize_url("key123", "https://example.com/callback", scope="video.publish")
    qs = parse_qs(urlparse(url).query)
    assert qs["scope"] == ["video.publish"]


def _make_token_session(json_body: dict, status_code: int = 200):
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = str(json_body)
    session.post.return_value = resp
    return session


def test_exchange_code_for_token_posts_expected_body():
    session = _make_token_session({"access_token": "at", "refresh_token": "rt", "expires_in": 86400})

    result = exchange_code_for_token(
        "the-code", "key123", "secret456", "https://example.com/callback", session=session
    )

    assert result["access_token"] == "at"
    sent = session.post.call_args.kwargs["data"]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "the-code"
    assert sent["client_key"] == "key123"
    assert sent["client_secret"] == "secret456"
    assert sent["redirect_uri"] == "https://example.com/callback"


def test_exchange_code_for_token_raises_on_bad_status():
    session = _make_token_session({"error": "invalid_grant"}, status_code=400)
    with pytest.raises(OAuthError):
        exchange_code_for_token("bad-code", "k", "s", "https://example.com/cb", session=session)


def test_exchange_code_for_token_raises_when_access_token_missing():
    session = _make_token_session({"refresh_token": "rt"})
    with pytest.raises(OAuthError):
        exchange_code_for_token("code", "k", "s", "https://example.com/cb", session=session)


def test_refresh_access_token_posts_expected_body():
    session = _make_token_session({"access_token": "new-at", "refresh_token": "new-rt"})

    result = refresh_access_token("old-rt", "key123", "secret456", session=session)

    assert result["access_token"] == "new-at"
    sent = session.post.call_args.kwargs["data"]
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "old-rt"


def test_refresh_access_token_raises_on_bad_status():
    session = _make_token_session({"error": "invalid_grant"}, status_code=401)
    with pytest.raises(OAuthError):
        refresh_access_token("expired-rt", "k", "s", session=session)
