"""Testes do cache negativo (não repetir busca no YouTube que acabou de falhar)
e da aceitação do exit code 101 do yt-dlp."""
import os
import time
from unittest.mock import MagicMock

from video_gen.gameplay import download_trailer_clip, unavailable_marker
from video_gen.music import download_ost_clip


def _fail_result():
    result = MagicMock()
    result.returncode = 1
    result.stderr = "Sign in to confirm your age"
    return result


def test_failed_search_is_not_retried_until_marker_expires(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path / "manual_empty")
    runner = MagicMock(return_value=_fail_result())

    assert download_trailer_clip("Blocked Game", runner=runner) is None
    assert unavailable_marker(tmp_path, "blocked-game").exists()
    assert download_trailer_clip("Blocked Game", runner=runner) is None
    assert runner.call_count == 1  # segunda chamada nem rodou o yt-dlp

    marker = unavailable_marker(tmp_path, "blocked-game")
    old = time.time() - 48 * 3600
    os.utime(marker, (old, old))
    download_trailer_clip("Blocked Game", runner=runner)
    assert runner.call_count == 2


def test_exit_code_101_counts_as_success_and_clears_marker(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path / "manual_empty")
    unavailable_marker(tmp_path, "some-game").touch()
    old = time.time() - 48 * 3600
    os.utime(unavailable_marker(tmp_path, "some-game"), (old, old))

    calls = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        result = MagicMock()
        result.stdout = "vid1 120\n" if "--print" in cmd else ""
        if "--print" in cmd:
            result.returncode = 0
        elif cmd[0] == "yt-dlp":
            result.returncode = 101
            (tmp_path / "some-game_raw.mp4").write_bytes(b"raw")
        else:
            result.returncode = 0
            (tmp_path / "some-game.mp4").write_bytes(b"final")
        return result

    result = download_trailer_clip("Some Game", runner=runner)

    assert result == tmp_path / "some-game.mp4"
    assert not unavailable_marker(tmp_path, "some-game").exists()
    assert calls[0][1].startswith("ytsearch5:")
    assert "--skip-download" in calls[0]


def test_search_without_extractable_result_marks_unavailable(tmp_path, monkeypatch):
    import video_gen.gameplay as gameplay_module

    monkeypatch.setattr(gameplay_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gameplay_module, "MANUAL_CLIPS_DIR", tmp_path / "manual_empty")
    empty = MagicMock()
    empty.returncode = 1
    empty.stdout = ""
    runner = MagicMock(return_value=empty)

    assert download_trailer_clip("Age Gated Game", runner=runner) is None
    assert unavailable_marker(tmp_path, "age-gated-game").exists()
    assert runner.call_count == 1  # só a busca; nada pra baixar


def test_section_from_middle_never_starts_at_zero_for_long_videos():
    from video_gen.gameplay import section_from_middle

    assert section_from_middle(200, 60) == "*90-150"
    assert section_from_middle(80, 60) == "*19-79"  # recua pra caber 60s, para 1s antes do fim
    assert section_from_middle(30, 60) == "*0-29"  # curto demais: pega (quase) tudo


def test_music_search_uses_negative_cache_too(tmp_path, monkeypatch):
    import video_gen.music as music_module

    monkeypatch.setattr(music_module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(music_module, "MANUAL_MUSIC_DIR", tmp_path / "manual_empty")
    runner = MagicMock(return_value=_fail_result())

    assert download_ost_clip("Blocked Game", runner=runner) is None
    assert download_ost_clip("Blocked Game", runner=runner) is None
    assert runner.call_count == 1
