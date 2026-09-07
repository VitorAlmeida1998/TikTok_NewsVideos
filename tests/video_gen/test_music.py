"""Testes do módulo de música de fundo (mock do subprocess runner, sem
chamadas reais a yt-dlp/ffmpeg/YouTube)."""
from unittest.mock import MagicMock

from video_gen.music import (
    download_ost_clip,
    find_cached_track,
    find_manual_track,
)


def test_find_cached_track_returns_none_when_missing(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    assert find_cached_track("Some Game") is None


def test_find_cached_track_returns_path_when_present(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    cached_file = tmp_path / "some-game.mp3"
    cached_file.write_bytes(b"fake")

    result = find_cached_track("Some Game")
    assert result == cached_file


def test_find_manual_track_returns_none_when_missing(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path)
    assert find_manual_track("Some Game") is None


def test_find_manual_track_finds_mp3(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path)
    manual_file = tmp_path / "some-game.mp3"
    manual_file.write_bytes(b"fake")

    assert find_manual_track("Some Game") == manual_file


def test_find_manual_track_finds_alternate_extensions(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path)
    manual_file = tmp_path / "some-game.wav"
    manual_file.write_bytes(b"fake")

    assert find_manual_track("Some Game") == manual_file


def test_download_ost_clip_returns_cached_without_calling_runner(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    cached_file = tmp_path / "some-game.mp3"
    cached_file.write_bytes(b"fake")

    runner = MagicMock()
    result = download_ost_clip("Some Game", runner=runner)

    assert result == cached_file
    runner.assert_not_called()


def test_download_ost_clip_prefers_manual_over_download(tmp_path, monkeypatch):
    import video_gen.music as music_module

    cache_dir = tmp_path / "cache"
    manual_dir = tmp_path / "manual"
    monkeypatch.setattr(music_module, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", manual_dir)
    manual_dir.mkdir()
    manual_file = manual_dir / "some-game.mp3"
    manual_file.write_bytes(b"manual track data")

    def fake_runner(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        final_path = cache_dir / "some-game.mp3"
        final_path.write_bytes(b"processed track")
        return result

    result = download_ost_clip("Some Game", runner=fake_runner)

    assert result is not None
    assert result == cache_dir / "some-game.mp3"


def test_download_ost_clip_falls_back_to_manual_when_download_would_fail(
    tmp_path, monkeypatch
):
    import video_gen.music as music_module

    cache_dir = tmp_path / "cache"
    manual_dir = tmp_path / "manual"
    monkeypatch.setattr(music_module, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", manual_dir)
    manual_dir.mkdir()
    manual_file = manual_dir / "restricted-game.wav"
    manual_file.write_bytes(b"manual track data")

    call_log = []

    def fake_runner(cmd, **kwargs):
        call_log.append(cmd[0])
        result = MagicMock()
        result.returncode = 0
        final_path = cache_dir / "restricted-game.mp3"
        final_path.write_bytes(b"processed track")
        return result

    result = download_ost_clip("Restricted Game", runner=fake_runner)

    assert result is not None
    assert "yt-dlp" not in call_log  # manual tem prioridade, yt-dlp nem é chamado


def test_download_ost_clip_returns_none_on_download_failure(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path / "manual_empty")

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "video unavailable"
    runner = MagicMock(return_value=fail_result)

    result = download_ost_clip("Nonexistent Game 12345", runner=runner)
    assert result is None


def test_download_ost_clip_returns_none_on_exception(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path / "manual_empty")

    def raising_runner(cmd, **kwargs):
        raise RuntimeError("yt-dlp not found")

    result = download_ost_clip("Some Game", runner=raising_runner)
    assert result is None


def test_download_ost_clip_success_creates_final_file(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path / "manual_empty")

    call_count = {"n": 0}

    def fake_runner(cmd, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        result.returncode = 0
        if call_count["n"] == 1:
            raw_path = tmp_path / "some-game_raw.m4a"
            raw_path.write_bytes(b"raw audio data")
        else:
            final_path = tmp_path / "some-game.mp3"
            final_path.write_bytes(b"converted audio data")
        return result

    result = download_ost_clip("Some Game", runner=fake_runner)

    assert result is not None
    assert result.name == "some-game.mp3"
    assert result.exists()
    assert not (tmp_path / "some-game_raw.m4a").exists()  # raw foi removido
    assert call_count["n"] == 2  # yt-dlp + ffmpeg
