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
import time
from pathlib import Path

logger = logging.getLogger("video_gen.gameplay")

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "gameplay_cache"
MANUAL_CLIPS_DIR = PROJECT_ROOT / "video_gen" / "manual_clips"

# Busca os N primeiros resultados e fica com o primeiro que baixar: se o
# trailer mais bem ranqueado tiver restrição de idade (falha, não contornamos),
# o yt-dlp simplesmente passa pro próximo resultado oficial.
SEARCH_RESULTS = 5
# yt-dlp pode sair com 101 (limite de downloads atingido) — é sucesso.
YTDLP_OK_RETURNCODES = (0, 101)
# Depois de uma busca sem resultado, não tenta de novo por esse tempo (o cron
# roda a cada 30 min; sem isso a mesma busca falha repetidamente no YouTube).
UNAVAILABLE_RETRY_HOURS = 24
# O trecho baixado começa no MEIO do vídeo (fração da duração): o começo de
# trailer é logo/classificação etária/tela preta, e o começo de OST é intro
# lenta. Nunca pega o início. Clipes manuais/upload não passam por isso (o
# usuário escolhe o início no painel).
MIDDLE_START_FRACTION = 0.45


def unavailable_marker(cache_dir: Path, slug: str) -> Path:
    return cache_dir / f"{slug}.unavailable"


def recently_unavailable(cache_dir: Path, slug: str) -> bool:
    marker = unavailable_marker(cache_dir, slug)
    if not marker.exists():
        return False
    return (time.time() - marker.stat().st_mtime) < UNAVAILABLE_RETRY_HOURS * 3600


def mark_unavailable(cache_dir: Path, slug: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    unavailable_marker(cache_dir, slug).touch()


def section_from_middle(duration: float, clip_seconds: int) -> str:
    """Expressão de --download-sections começando em MIDDLE_START_FRACTION da
    duração, recuada se não couber `clip_seconds` até o fim (vídeo curto
    demais começa do 0). O fim para 1s antes da duração declarada: pedir
    exatamente até o último segundo faz o yt-dlp/ffmpeg devolver arquivo
    vazio em alguns streams DASH."""
    end_limit = max(1.0, duration - 1.0)
    start = max(0.0, min(duration * MIDDLE_START_FRACTION, end_limit - clip_seconds))
    end = min(start + clip_seconds, end_limit)
    return f"*{start:.0f}-{end:.0f}"


def find_youtube_candidate(query: str, match_filters: str, runner, timeout: int) -> tuple[str, float] | None:
    """Faz a busca no YouTube sem baixar e devolve (video_id, duração) do
    primeiro resultado que o yt-dlp consegue extrair (um resultado com
    restrição de idade falha na extração e é simplesmente pulado — nunca
    tentamos contornar o gate)."""
    cmd = [
        "yt-dlp",
        query,
        "--js-runtimes",
        "deno",
        "--skip-download",
        "--match-filters",
        match_filters,
        "--print",
        "%(id)s %(duration)s",
    ]
    result = runner(cmd, timeout=timeout)
    for line in (getattr(result, "stdout", "") or "").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        video_id, duration = parts
        try:
            return video_id, float(duration)
        except ValueError:
            continue
    return None

# Duração do clipe baixado: longa o suficiente para cobrir a narração
# inteira sem precisar repetir (loop) no meio do vídeo — narrações
# costumam durar 20-40s, então 60s cobre a grande maioria sem "costura"
# visível de loop. Só entra em loop se a narração for excepcionalmente
# longa (>60s).
CLIP_DURATION_SECONDS = 60

# Extensões de vídeo aceitas para clipes manuais (qualquer uma que o ffmpeg leia).
MANUAL_CLIP_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".avi"]


def slugify(game_name: str) -> str:
    """Normaliza o nome do jogo para um slug seguro de nome de arquivo.

    Truncado em 100 caracteres: nomes de jogo absurdamente longos (ex: título
    de notícia usado por engano como game_name) poderiam gerar um nome de
    arquivo que excede o limite do filesystem (geralmente 255 bytes),
    causando "File name too long" no ffmpeg ao salvar no cache.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", game_name.lower()).strip("-")
    slug = slug[:100].strip("-")
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
    game_name: str, timeout: int = 180, runner=None
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

    if recently_unavailable(CACHE_DIR, slug):
        logger.info("Busca de trailer para '%s' falhou há menos de %dh, não tentando de novo",
                    game_name, UNAVAILABLE_RETRY_HOURS)
        return None

    query = f"ytsearch{SEARCH_RESULTS}:{game_name} official trailer"

    try:
        # evita "all cutscenes 4 hours" e lives; trailers têm poucos minutos
        candidate = find_youtube_candidate(query, "duration<900 & !is_live", runner, timeout)
        if candidate is None:
            mark_unavailable(CACHE_DIR, slug)
            logger.warning(
                "Nenhum trailer extraível no YouTube para '%s' (restrição de idade?). "
                "Envie um vídeo de fundo pelo painel ou coloque um clipe manual em "
                "video_gen/manual_clips/%s.mp4",
                game_name,
                slug,
            )
            return None
        video_id, duration = candidate
        section = section_from_middle(duration, CLIP_DURATION_SECONDS)
        download_cmd = [
            "yt-dlp",
            f"https://www.youtube.com/watch?v={video_id}",
            "--js-runtimes",
            "deno",
            "-f",
            "bestvideo[height<=1080][ext=mp4]/best[ext=mp4]",
            "--download-sections",
            section,
            "-o",
            str(raw_path),
        ]
        logger.info("Baixando trailer %s de '%s' (duração %.0fs, trecho %s)", video_id, game_name, duration, section)
        result = runner(download_cmd, timeout=timeout)
    except Exception:
        logger.exception("Falha ao rodar yt-dlp para '%s'", game_name)
        return None

    if result.returncode not in YTDLP_OK_RETURNCODES or not raw_path.exists():
        mark_unavailable(CACHE_DIR, slug)
        logger.warning(
            "yt-dlp não encontrou/baixou trailer para '%s' (returncode=%s): %s. "
            "Se for restrição de idade, envie um vídeo de fundo pelo painel ou coloque "
            "um clipe manual em video_gen/manual_clips/%s.mp4",
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
        logger.warning(
            "Falha ao recortar clipe para '%s': %s",
            game_name,
            getattr(crop_result, "stderr", "")[-400:],
        )
        return None

    unavailable_marker(CACHE_DIR, slug).unlink(missing_ok=True)
    logger.info("Clipe de gameplay pronto para '%s': %s", game_name, final_path)
    return final_path
