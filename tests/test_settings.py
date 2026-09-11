"""Testes das configurações editáveis pelo painel."""
from shared.settings import DEFAULTS, get_voice_id, load_settings, save_settings


def test_load_returns_defaults_when_file_missing(tmp_path):
    assert load_settings(tmp_path / "nope.json") == DEFAULTS


def test_save_persists_known_keys_and_ignores_unknown(tmp_path):
    path = tmp_path / "settings.json"
    saved = save_settings({"voice_id": "abc123", "hackeado": "não"}, path)

    assert saved["voice_id"] == "abc123"
    assert "hackeado" not in saved
    assert load_settings(path)["voice_id"] == "abc123"
    assert load_settings(path)["posts_per_day"] == DEFAULTS["posts_per_day"]


def test_load_falls_back_to_defaults_on_corrupt_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ isso não é json", encoding="utf-8")
    assert load_settings(path) == DEFAULTS


def test_get_voice_id_prefers_settings_then_env(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    assert get_voice_id(path) == "pNInz6obpgDQGcFmaJgB"

    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "do-env")
    assert get_voice_id(path) == "do-env"

    save_settings({"voice_id": "do-painel"}, path)
    assert get_voice_id(path) == "do-painel"
