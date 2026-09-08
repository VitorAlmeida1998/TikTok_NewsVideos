"""Processamento de mídia enviada pelo usuário via front-end (webapp): corta
um vídeo/áudio no trecho escolhido (início + duração) e salva DIRETO no
cache automático (data/gameplay_cache/ ou data/music_cache/), que já tem
prioridade máxima de leitura em video_gen/gameplay.py e video_gen/music.py
(find_cached_clip / find_cached_track são checados antes de qualquer coisa).

Isso significa que um upload feito pelo usuário sempre "vence" — sobrescreve
qualquer clipe automático baixado anteriormente via yt-dlp para aquele jogo.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from video_gen.gameplay import CACHE_DIR as GAMEPLAY_CACHE_DIR
from video_gen.gameplay import slugify
from video_gen.music import CACHE_DIR as MUSIC_CACHE_DIR

logger = logging.getLogger("webapp.media")

PROJECT_ROOT = Path(__file__).parent.parent
UPLOAD_STAGING_DIR = PROJECT_ROOT / "data" / "uploads_staging"

MAX_CLIP_SECONDS = 180  # limite de segurança para o corte pedido pelo usuário


class MediaProcessingError(Exception):
    pass


def _run_ffmpeg(cmd: list[str], timeout: int = 120) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        logger.error("ffmpeg falhou: %s", result.stderr[-2000:])
        raise MediaProcessingError(f"ffmpeg falhou: {result.stderr[-500:]}")


def process_uploaded_video(
    source_path: str | Path,
    game_name: str,
    start_seconds: float = 0.0,
    duration_seconds: float = 60.0,
) -> Path:
    """Corta o vídeo enviado no trecho [start, start+duration], recorta/escala
    para 9:16 (1080x1920) com frame rate constante (30fps, evita flicker) e
    salva em data/gameplay_cache/<slug>.mp4 — prioridade máxima de leitura.

    Retorna o path final.
    """
    duration_seconds = max(1.0, min(duration_seconds, MAX_CLIP_SECONDS))
    start_seconds = max(0.0, start_seconds)

    source_duration = probe_duration_seconds(source_path)
    if source_duration is None:
        raise MediaProcessingError(
            "Não foi possível ler o arquivo enviado — verifique se é um vídeo válido."
        )
    if start_seconds >= source_duration:
        raise MediaProcessingError(
            f"O início do trecho ({start_seconds:.1f}s) é maior ou igual à duração do "
            f"vídeo enviado ({source_duration:.1f}s) — escolha um início menor."
        )

    slug = slugify(game_name)
    GAMEPLAY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    final_path = GAMEPLAY_CACHE_DIR / f"{slug}.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-i",
        str(source_path),
        "-vf",
        "crop=ih*9/16:ih,scale=1080:1920",
        "-r",
        "30",
        "-an",
        "-t",
        str(duration_seconds),
        str(final_path),
    ]
    _run_ffmpeg(cmd)

    if not final_path.exists():
        raise MediaProcessingError("ffmpeg não gerou o arquivo final")

    output_duration = probe_duration_seconds(final_path)
    if not output_duration or output_duration < 0.5:
        final_path.unlink(missing_ok=True)
        raise MediaProcessingError(
            "O corte resultou num arquivo vazio/inválido — verifique o início e a duração "
            "do trecho em relação à duração real do vídeo enviado."
        )

    logger.info(
        "Vídeo de fundo customizado salvo para '%s': %s (%.1fs a partir de %.1fs)",
        game_name,
        final_path,
        duration_seconds,
        start_seconds,
    )
    return final_path


def process_uploaded_audio(
    source_path: str | Path,
    game_name: str,
    start_seconds: float = 0.0,
    duration_seconds: float = 60.0,
) -> Path:
    """Corta o áudio enviado no trecho [start, start+duration], converte para
    mp3 e salva em data/music_cache/<slug>.mp3 — prioridade máxima de leitura.

    Retorna o path final.
    """
    duration_seconds = max(1.0, min(duration_seconds, MAX_CLIP_SECONDS))
    start_seconds = max(0.0, start_seconds)

    source_duration = probe_duration_seconds(source_path)
    if source_duration is None:
        raise MediaProcessingError(
            "Não foi possível ler o arquivo enviado — verifique se é um áudio válido."
        )
    if start_seconds >= source_duration:
        raise MediaProcessingError(
            f"O início do trecho ({start_seconds:.1f}s) é maior ou igual à duração do "
            f"áudio enviado ({source_duration:.1f}s) — escolha um início menor."
        )

    slug = slugify(game_name)
    MUSIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    final_path = MUSIC_CACHE_DIR / f"{slug}.mp3"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_seconds),
        "-i",
        str(source_path),
        "-t",
        str(duration_seconds),
        str(final_path),
    ]
    _run_ffmpeg(cmd)

    if not final_path.exists():
        raise MediaProcessingError("ffmpeg não gerou o arquivo final")

    output_duration = probe_duration_seconds(final_path)
    if not output_duration or output_duration < 0.5:
        final_path.unlink(missing_ok=True)
        raise MediaProcessingError(
            "O corte resultou num arquivo vazio/inválido — verifique o início e a duração "
            "do trecho em relação à duração real do áudio enviado."
        )

    logger.info(
        "Música de fundo customizada salva para '%s': %s (%.1fs a partir de %.1fs)",
        game_name,
        final_path,
        duration_seconds,
        start_seconds,
    )
    return final_path


def probe_duration_seconds(path: str | Path) -> float | None:
    """Retorna a duração em segundos de um arquivo de mídia via ffprobe, ou
    None se não conseguir determinar (arquivo inválido/corrompido).
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return None


def clear_gameplay_cache(game_name: str) -> None:
    """Remove o clipe em cache (automático ou vindo de upload) para um jogo,
    forçando nova busca automática via yt-dlp na próxima geração de vídeo.
    """
    slug = slugify(game_name)
    path = GAMEPLAY_CACHE_DIR / f"{slug}.mp4"
    path.unlink(missing_ok=True)


def clear_music_cache(game_name: str) -> None:
    """Remove a faixa em cache (automática ou vinda de upload) para um jogo,
    forçando nova busca automática via yt-dlp na próxima geração de vídeo.
    """
    slug = slugify(game_name)
    path = MUSIC_CACHE_DIR / f"{slug}.mp3"
    path.unlink(missing_ok=True)
