"""Busca e prepara clipes de gameplay/trailer oficial para usar como fundo
do vídeo (via yt-dlp), com fallback seguro para fundo gradiente se não
encontrar/baixar.

IMPORTANTE (uso responsável):
- Buscamos apenas trailers/vídeos OFICIAIS do canal do publisher/estúdio
  (a query inclui "official trailer"), nunca clipes de terceiros ou
  material de matérias jornalísticas — seguindo a regra do projeto.
- Baixar vídeo do YouTube via yt-dlp está numa área cinzenta em relação
  aos Termos de Serviço do YouTube, mesmo para trailers oficiais. Usamos
  apenas clipes curtos (poucos segundos) como plano de fundo, mas isso
  não elimina o risco de ToS. Se isso for um problema, trocar por uma
  biblioteca de clipes próprios (ver README) é a alternativa mais segura.
- Cache local em data/gameplay_cache/<slug-do-jogo>.mp4 evita rebaixar o
  mesmo jogo repetidamente.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger("video_gen.gameplay")

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "gameplay_cache"

CLIP_START_SECONDS = 8  # pula a intro/logo dos trailers
CLIP_DURATION_SECONDS = 12  # clipe curto, suficiente para looping no vídeo


def slugify(game_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", game_name.lower()).strip("-")
    return slug or "unknown"


def find_cached_clip(game_name: str) -> Path | None:
    """Retorna o clipe já baixado/preparado para esse jogo, se existir."""
    path = CACHE_DIR / f"{slugify(game_name)}.mp4"
    return path if path.exists() else None


def download_trailer_clip(
    game_name: str, timeout: int = 90, runner=None
) -> Path | None:
    """Busca "<game_name> official trailer" no YouTube, baixa um trecho curto
    (via yt-dlp --download-sections) e recorta/escala para 9:16 (1080x1920)
    com ffmpeg. Retorna o path do clipe pronto, ou None se falhar (fallback
    para fundo gradiente deve ser tratado pelo chamador).

    `runner` pode ser injetado para testes: callable(cmd: list[str]) ->
    subprocess.CompletedProcess-like (precisa .returncode e .stderr).
    """
    cached = find_cached_clip(game_name)
    if cached:
        logger.info("Usando clipe em cache para '%s': %s", game_name, cached)
        return cached

    runner = runner or (lambda cmd, **kw: subprocess.run(cmd, capture_output=True, text=True, **kw))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(game_name)
    raw_path = CACHE_DIR / f"{slug}_raw.mp4"
    final_path = CACHE_DIR / f"{slug}.mp4"

    query = f"ytsearch1:{game_name} official trailer"
    section = f"*{CLIP_START_SECONDS}-{CLIP_START_SECONDS + CLIP_DURATION_SECONDS}"

    download_cmd = [
        "yt-dlp",
        query,
        "--js-runtimes",
        "deno",
        "-f",
        "bestvideo[height<=1080][ext=mp4]/best[ext=mp4]",
        "--download-sections",
        section,
        "-o",
        str(raw_path),
    ]

    try:
        result = runner(download_cmd, timeout=timeout)
    except Exception:
        logger.exception("Falha ao rodar yt-dlp para '%s'", game_name)
        return None

    if result.returncode != 0 or not raw_path.exists():
        logger.warning(
            "yt-dlp não encontrou/baixou trailer para '%s' (returncode=%s): %s",
            game_name,
            getattr(result, "returncode", "?"),
            getattr(result, "stderr", "")[-500:],
        )
        return None

    # Recorta/escala para 9:16 (1080x1920): crop central + scale.
    crop_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-vf",
        "crop=ih*9/16:ih,scale=1080:1920",
        "-an",  # remove áudio do trailer (a narração TTS é o áudio principal)
        "-t",
        str(CLIP_DURATION_SECONDS),
        str(final_path),
    ]
    crop_result = runner(crop_cmd, timeout=timeout)
    raw_path.unlink(missing_ok=True)

    if crop_result.returncode != 0 or not final_path.exists():
        logger.warning("Falha ao recortar clipe para '%s'", game_name)
        return None

    logger.info("Clipe de gameplay pronto para '%s': %s", game_name, final_path)
    return final_path
