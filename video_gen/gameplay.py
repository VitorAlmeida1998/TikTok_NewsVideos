"""Busca e prepara clipes de gameplay/trailer oficial para usar como fundo
do vídeo, com esta ordem de prioridade:

1. Clipe MANUAL fornecido pelo usuário em video_gen/manual_clips/<slug>.mp4
   (sempre checado primeiro — nunca sobrescrito, nunca expira)
2. Clipe já em cache (baixado anteriormente via yt-dlp)
3. Download automático via yt-dlp (trailer oficial no YouTube)
4. Fallback: fundo gradiente (tratado pelo chamador se tudo isso retornar None)

IMPORTANTE (uso responsável):
- Buscamos apenas trailers/vídeos OFICIAIS do canal do publisher/estúdio
  (a query inclui "official trailer"), nunca clipes de terceiros ou
  material de matérias jornalísticas — seguindo a regra do projeto.
- Baixar vídeo do YouTube via yt-dlp está numa área cinzenta em relação
  aos Termos de Serviço do YouTube, mesmo para trailers oficiais. Usamos
  apenas clipes curtos (poucos segundos) como plano de fundo.
- Vídeos com restrição de idade no YouTube exigem login para assistir —
  este projeto NUNCA tenta contornar essa verificação (sem cookies de
  sessão, sem login automatizado). Nesses casos o download falha e cai
  no fallback gradiente, a menos que exista um clipe manual para o jogo.
- Cache automático em data/gameplay_cache/<slug-do-jogo>.mp4 evita
  rebaixar o mesmo jogo repetidamente.
- Clipes manuais em video_gen/manual_clips/<slug-do-jogo>.mp4: pasta para
  o usuário colocar seus próprios clipes (gravados/baixados por ele,
  fora deste sistema) — útil para jogos com trailer restrito por idade
  no YouTube. Use `slugify(nome_do_jogo)` para saber o nome exato do
  arquivo esperado. Qualquer formato de vídeo aceito pelo ffmpeg funciona;
  será recortado/escalado para 9:16 automaticamente, igual aos baixados.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger("video_gen.gameplay")

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "gameplay_cache"
MANUAL_CLIPS_DIR = PROJECT_ROOT / "video_gen" / "manual_clips"

CLIP_START_SECONDS = 8  # pula a intro/logo dos trailers
CLIP_DURATION_SECONDS = 12  # clipe curto, suficiente para looping no vídeo

# Extensões de vídeo aceitas para clipes manuais (qualquer uma que o ffmpeg leia).
MANUAL_CLIP_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".avi"]


def slugify(game_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", game_name.lower()).strip("-")
    return slug or "unknown"


def find_cached_clip(game_name: str) -> Path | None:
    """Retorna o clipe já baixado/preparado (cache automático) para esse jogo, se existir."""
    path = CACHE_DIR / f"{slugify(game_name)}.mp4"
    return path if path.exists() else None


def find_manual_clip(game_name: str) -> Path | None:
    """Retorna o clipe fornecido manualmente pelo usuário para esse jogo, se existir.

    Procura em video_gen/manual_clips/<slug>.<ext> para cada extensão aceita.
    """
    slug = slugify(game_name)
    for ext in MANUAL_CLIP_EXTENSIONS:
        candidate = MANUAL_CLIPS_DIR / f"{slug}{ext}"
        if candidate.exists():
            return candidate
    return None


def _prepare_manual_clip(source_path: Path, game_name: str, timeout: int, runner) -> Path | None:
    """Recorta/escala um clipe manual para 9:16 e salva no cache automático,
    para não reprocessar a cada vídeo gerado. Retorna o path processado.
    """
    slug = slugify(game_name)
    final_path = CACHE_DIR / f"{slug}.mp4"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    crop_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vf",
        "crop=ih*9/16:ih,scale=1080:1920",
        "-r",
        "30",
        "-an",
        "-t",
        str(CLIP_DURATION_SECONDS),
        str(final_path),
    ]
    result = runner(crop_cmd, timeout=timeout)

    if result.returncode != 0 or not final_path.exists():
        logger.warning("Falha ao processar clipe manual para '%s'", game_name)
        return None

    logger.info("Clipe manual processado e cacheado para '%s': %s", game_name, final_path)
    return final_path


def download_trailer_clip(
    game_name: str, timeout: int = 90, runner=None
) -> Path | None:
    """Retorna um clipe de fundo pronto (9:16) para o jogo, na seguinte ordem:
    1. Clipe manual do usuário (video_gen/manual_clips/) — processado e cacheado
       na primeira vez que for usado.
    2. Clipe já em cache de uma busca anterior.
    3. Busca "<game_name> official trailer" no YouTube via yt-dlp, baixa um
       trecho curto e recorta/escala para 9:16.

    Retorna None se nenhuma fonte disponibilizar o clipe (fallback para fundo
    gradiente deve ser tratado pelo chamador). NUNCA tenta contornar
    verificação de idade/login do YouTube.

    `runner` pode ser injetado para testes: callable(cmd: list[str]) ->
    subprocess.CompletedProcess-like (precisa .returncode e .stderr).
    """
    runner = runner or (lambda cmd, **kw: subprocess.run(cmd, capture_output=True, text=True, **kw))

    cached = find_cached_clip(game_name)
    if cached:
        logger.info("Usando clipe em cache para '%s': %s", game_name, cached)
        return cached

    manual = find_manual_clip(game_name)
    if manual:
        logger.info("Usando clipe MANUAL fornecido pelo usuário para '%s': %s", game_name, manual)
        return _prepare_manual_clip(manual, game_name, timeout, runner)

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
            "yt-dlp não encontrou/baixou trailer para '%s' (returncode=%s): %s. "
            "Se for restrição de idade, coloque um clipe manual em "
            "video_gen/manual_clips/%s.mp4",
            game_name,
            getattr(result, "returncode", "?"),
            getattr(result, "stderr", "")[-500:],
            slug,
        )
        return None

    # Recorta/escala para 9:16 (1080x1920): crop central + scale.
    # -r 30 força frame rate constante (CFR) igual ao da composição Remotion
    # (FPS=30 em Root.tsx) — trailers do YouTube costumam vir com frame rate
    # variável (VFR), que causa flicker/frames pretos piscando no render.
    crop_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-vf",
        "crop=ih*9/16:ih,scale=1080:1920",
        "-r",
        "30",
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
