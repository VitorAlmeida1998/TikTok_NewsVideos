"""Testes do processamento de mídia enviada (webapp/media.py): valida os
casos de borda que causavam bugs reais (arquivo corrompido -> 500,
start_seconds além da duração real -> arquivo vazio aceito silenciosamente).
"""
import subprocess

import pytest

from webapp.media import (
    MediaProcessingError,
    process_uploaded_audio,
    process_uploaded_video,
)


def _make_test_video(path, duration=5):
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
            "-c:v", "libx264", str(path),
        ],
        capture_output=True, timeout=30, check=True,
    )


def _make_test_audio(path, duration=5):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", str(path)],
        capture_output=True, timeout=30, check=True,
    )


@pytest.fixture(autouse=True)
def _patch_cache_dirs(tmp_path, monkeypatch):
    import webapp.media as media_module

    monkeypatch.setattr(media_module, "GAMEPLAY_CACHE_DIR", tmp_path / "gameplay_cache")
    monkeypatch.setattr(media_module, "MUSIC_CACHE_DIR", tmp_path / "music_cache")


def test_process_video_happy_path(tmp_path):
    src = tmp_path / "src.mp4"
    _make_test_video(src, duration=10)

    result = process_uploaded_video(src, "Test Game", start_seconds=1, duration_seconds=5)
    assert result.exists()


def test_process_video_rejects_corrupted_file(tmp_path):
    src = tmp_path / "fake.mp4"
    src.write_text("isso não é um vídeo de verdade")

    with pytest.raises(MediaProcessingError):
        process_uploaded_video(src, "Test Game", start_seconds=0, duration_seconds=5)


def test_process_video_rejects_start_beyond_duration(tmp_path):
    """Regressão: start_seconds >= duração real gerava um arquivo mp4 vazio
    (262 bytes, sem stream de vídeo) que era aceito como sucesso."""
    src = tmp_path / "short.mp4"
    _make_test_video(src, duration=5)

    with pytest.raises(MediaProcessingError, match="maior ou igual"):
        process_uploaded_video(src, "Test Game", start_seconds=100, duration_seconds=5)


def test_process_audio_rejects_start_beyond_duration(tmp_path):
    src = tmp_path / "short.mp3"
    _make_test_audio(src, duration=5)

    with pytest.raises(MediaProcessingError, match="maior ou igual"):
        process_uploaded_audio(src, "Test Game", start_seconds=100, duration_seconds=5)


def test_process_video_does_not_leave_broken_file_in_cache(tmp_path):
    """Após a rejeição, o cache não deve ficar com um arquivo quebrado."""
    import webapp.media as media_module

    src = tmp_path / "short.mp4"
    _make_test_video(src, duration=5)

    with pytest.raises(MediaProcessingError):
        process_uploaded_video(src, "Broken Game", start_seconds=100, duration_seconds=5)

    final_path = media_module.GAMEPLAY_CACHE_DIR / "broken-game.mp4"
    assert not final_path.exists()
