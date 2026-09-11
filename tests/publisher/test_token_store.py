"""Testes do armazenamento local de tokens do TikTok (arquivo JSON isolado em tmp_path)."""
import time

from publisher.token_store import is_expired, load_tokens, save_tokens


def test_load_tokens_returns_none_when_file_missing(tmp_path):
    path = str(tmp_path / "tokens.json")
    assert load_tokens(path) is None


def test_save_and_load_tokens_roundtrip(tmp_path):
    path = str(tmp_path / "tokens.json")
    save_tokens(access_token="at", refresh_token="rt", expires_in=86400, path=path)

    loaded = load_tokens(path)
    assert loaded["access_token"] == "at"
    assert loaded["refresh_token"] == "rt"
    assert loaded["expires_at"] > time.time()


def test_is_expired_true_for_past_timestamp():
    assert is_expired({"expires_at": time.time() - 10}) is True


def test_is_expired_false_for_future_timestamp():
    assert is_expired({"expires_at": time.time() + 3600}) is False


def test_is_expired_true_when_missing_expires_at():
    assert is_expired({}) is True


def test_save_tokens_applies_expiry_margin(tmp_path):
    path = str(tmp_path / "tokens.json")
    before = time.time()
    save_tokens(access_token="at", refresh_token="rt", expires_in=1000, path=path)
    loaded = load_tokens(path)

    # expires_at deve ser aproximadamente before + 1000 - 300 (margem de segurança).
    assert loaded["expires_at"] < before + 1000
    assert loaded["expires_at"] > before + 600
