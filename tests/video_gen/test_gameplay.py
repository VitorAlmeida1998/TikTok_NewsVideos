"""Testes do módulo de gameplay/trailer (mock do subprocess runner, sem
chamadas reais a yt-dlp/ffmpeg/YouTube)."""
from unittest.mock import MagicMock

from video_gen.gameplay import (
    download_trailer_clip,
    find_cached_clip,
    find_manual_clip,
    slugify,
)


def test_slugify_normalizes_game_name():
    assert slugify("Forza Horizon 6") == "forza-horizon-6"
    assert slugify("Grand Theft Auto VI!!") == "grand-theft-auto-vi"
    assert slugify("") == "unknown"


def test_find_cached_clip_returns_none_when_missing(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    assert find_cached_clip("Some Game") is None


def test_find_cached_clip_returns_path_when_present(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    cached_file = tmp_path / "some-game.mp4"
    cached_file.write_bytes(b"fake")

    result = find_cached_clip("Some Game")
    assert result == cached_file


def test_find_manual_clip_returns_none_when_missing(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path)
    assert find_manual_clip("Some Game") is None


def test_find_manual_clip_finds_mp4(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path)
    manual_file = tmp_path / "some-game.mp4"
    manual_file.write_bytes(b"fake")

    assert find_manual_clip("Some Game") == manual_file


def test_find_manual_clip_finds_alternate_extensions(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path)
    manual_file = tmp_path / "some-game.mov"
    manual_file.write_bytes(b"fake")

    assert find_manual_clip("Some Game") == manual_file


def test_download_trailer_clip_returns_cached_without_calling_runner(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    cached_file = tmp_path / "some-game.mp4"
    cached_file.write_bytes(b"fake")

    runner = MagicMock()
    result = download_trailer_clip("Some Game", runner=runner)

    assert result == cached_file
    runner.assert_not_called()


def test_download_trailer_clip_prefers_manual_over_download(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    cache_dir = tmp_path / "cache"
    manual_dir = tmp_path / "manual"
    monkeypatch.setattr(gameplay_module, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", manual_dir)
    manual_dir.mkdir()
    manual_file = manual_dir / "some-game.mp4"
    manual_file.write_bytes(b"manual clip data")

    def fake_runner(cmd, **kwargs):
        # simula o ffmpeg processando o clipe manual (único subprocess chamado)
        result = MagicMock()
        result.returncode = 0
        final_path = cache_dir / "some-game.mp4"
        final_path.write_bytes(b"processed clip")
        return result

    result = download_trailer_clip("Some Game", runner=fake_runner)

    assert result is not None
    assert result == cache_dir / "some-game.mp4"
    # yt-dlp nunca foi chamado (só o ffmpeg do processamento manual)


def test_download_trailer_clip_falls_back_to_manual_when_download_would_fail(
    tmp_path, monkeypatch
):
    import video_gen.gameplay as gameplay_module

    cache_dir = tmp_path / "cache"
    manual_dir = tmp_path / "manual"
    monkeypatch.setattr(gameplay_module, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", manual_dir)
    manual_dir.mkdir()
    manual_file = manual_dir / "restricted-game.mov"
    manual_file.write_bytes(b"manual clip data")

    call_log = []

    def fake_runner(cmd, **kwargs):
        call_log.append(cmd[0])
        result = MagicMock()
        result.returncode = 0
        final_path = cache_dir / "restricted-game.mp4"
        final_path.write_bytes(b"processed clip")
        return result

    result = download_trailer_clip("Restricted Game", runner=fake_runner)

    assert result is not None
    assert "yt-dlp" not in call_log  # manual tem prioridade, yt-dlp nem é chamado


def test_download_trailer_clip_returns_none_on_download_failure(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path / "manual_empty")

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "video unavailable"
    runner = MagicMock(return_value=fail_result)

    result = download_trailer_clip("Nonexistent Game 12345", runner=runner)
    assert result is None


def test_download_trailer_clip_returns_none_on_exception(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path / "manual_empty")

    def raising_runner(cmd, **kwargs):
        raise RuntimeError("yt-dlp not found")

    result = download_trailer_clip("Some Game", runner=raising_runner)
    assert result is None


def test_download_trailer_clip_success_creates_final_file(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path / "manual_empty")

    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        if "--print" in cmd:
            # busca: 1º resultado com restrição de idade (sem linha), 2º ok
            result.stdout = "abc123 200\n"
        elif cmd[0] == "yt-dlp":
            # simula o yt-dlp criando o arquivo raw
            (tmp_path / "some-game_raw.mp4").write_bytes(b"raw video data")
        else:
            # simula o ffmpeg criando o arquivo final
            (tmp_path / "some-game.mp4").write_bytes(b"cropped video data")
        return result

    result = download_trailer_clip("Some Game", runner=fake_runner)

    assert result is not None
    assert result.name == "some-game.mp4"
    assert result.exists()
    assert not (tmp_path / "some-game_raw.mp4").exists()  # raw foi removido
    assert len(calls) == 3  # busca + download + ffmpeg
    assert calls[0][1].startswith("ytsearch5:")
    download = calls[1]
    assert download[1] == "https://www.youtube.com/watch?v=abc123"
    # 200s de vídeo: começa em 45% (90s), nunca no início
    assert download[download.index("--download-sections") + 1] == "*90-150"
