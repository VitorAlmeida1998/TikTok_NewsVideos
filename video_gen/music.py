"""Busca e prepara uma trilha musical de fundo (OST/tema do jogo) para tocar
por baixo da narração, com esta ordem de prioridade:

1. Faixa MANUAL fornecida pelo usuário em video_gen/manual_music/<slug>.*
   (sempre checada primeiro — nunca sobrescrita, nunca expira)
2. Faixa já em cache (baixada anteriormente via yt-dlp)
3. Download automático via yt-dlp (busca "<jogo> official soundtrack" /
   "main theme" no YouTube, extrai só o áudio)
4. Fallback: sem música de fundo (tratado pelo chamador se tudo isso
   retornar None) — o vídeo fica só com a narração, como já era antes.

IMPORTANTE (uso responsável / risco assumido pelo usuário):
- Trilhas sonoras oficiais de jogos são material com copyright do
  publisher/estúdio/compositor. Usar essa música num vídeo de TikTok é
  uma violação de direitos autorais na prática, mesmo mencionando a fonte
  — o TikTok pode aplicar Content ID/silenciar o áudio/derrubar o vídeo.
  Essa é uma decisão explícita do usuário sobre a própria conta, aceitando
  esse risco — igual usar imagem oficial de trailer, mas com risco maior
  por ser o áudio "identificável" por sistemas de audio fingerprinting.
- Regra que NÃO muda: nunca contornar verificação de idade/login do
  YouTube para baixar nada (sem cookies de sessão, sem conta automatizada).
  Se a busca de OST cair num vídeo com restrição de idade, o download
  falha e o vídeo fica sem música de fundo, a menos que exista uma faixa
  manual para o jogo.
- Cache automático em data/music_cache/<slug-do-jogo>.mp3 evita rebaixar
  a mesma trilha repetidamente.
- Faixas manuais em video_gen/manual_music/<slug-do-jogo>.<ext>: pasta
  para o usuário colocar sua própria música (comprada/licenciada/baixada
  por ele, fora deste sistema). Use `slugify(nome_do_jogo)` (mesma função
  usada em gameplay.py) para saber o nome exato do arquivo esperado.
  Qualquer formato de áudio aceito pelo ffmpeg funciona.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from video_gen.gameplay import slugify

logger = logging.getLogger("video_gen.music")

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "music_cache"
MANUAL_MUSIC_DIR = PROJECT_ROOT / "video_gen" / "manual_music"

CLIP_START_SECONDS = 5  # pula silêncio/intro de faixas de OST
# Duração da faixa baixada: longa o suficiente para cobrir a narração
# inteira sem repetir (loop) no meio do vídeo. Precisa bater com
# MUSIC_CLIP_DURATION_SECONDS em NewsShort.tsx.
CLIP_DURATION_SECONDS = 60

# Extensões de áudio aceitas para faixas manuais.
MANUAL_MUSIC_EXTENSIONS = [".mp3", ".m4a", ".wav", ".ogg", ".flac"]


def find_cached_track(game_name: str) -> Path | None:
    """Retorna a faixa já baixada/preparada (cache automático) para esse jogo, se existir."""
    path = CACHE_DIR / f"{slugify(game_name)}.mp3"
    return path if path.exists() else None


def find_manual_track(game_name: str) -> Path | None:
    """Retorna a faixa fornecida manualmente pelo usuário para esse jogo, se existir.

    Procura em video_gen/manual_music/<slug>.<ext> para cada extensão aceita.
    """
    slug = slugify(game_name)
    for ext in MANUAL_MUSIC_EXTENSIONS:
        candidate = MANUAL_MUSIC_DIR / f"{slug}{ext}"
        if candidate.exists():
            return candidate
    return None


def _prepare_manual_track(source_path: Path, game_name: str, timeout: int, runner) -> Path | None:
    """Converte/recorta uma faixa manual para mp3 e salva no cache automático,
    para não reprocessar a cada vídeo gerado. Retorna o path processado.
    """
    slug = slugify(game_name)
    final_path = CACHE_DIR / f"{slug}.mp3"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    convert_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-t",
        str(CLIP_DURATION_SECONDS),
        "-vn",
        str(final_path),
    ]
    result = runner(convert_cmd, timeout=timeout)

    if result.returncode != 0 or not final_path.exists():
        logger.warning("Falha ao processar faixa manual para '%s'", game_name)
        return None

    logger.info("Faixa manual processada e cacheada para '%s': %s", game_name, final_path)
    return final_path


def download_ost_clip(game_name: str, timeout: int = 180, runner=None) -> Path | None:
    """Retorna um trecho de música de fundo pronto (mp3) para o jogo, nesta ordem:
    1. Faixa manual do usuário (video_gen/manual_music/) — processada e cacheada
       na primeira vez que for usada.
    2. Faixa já em cache de uma busca anterior.
    3. Busca "<game_name> official soundtrack" no YouTube via yt-dlp, extrai
       só o áudio de um trecho curto.

    Retorna None se nenhuma fonte disponibilizar a faixa (o vídeo fica sem
    música de fundo — deve ser tratado pelo chamador). NUNCA tenta contornar
    verificação de idade/login do YouTube.

    `runner` pode ser injetado para testes: callable(cmd: list[str]) ->
    subprocess.CompletedProcess-like (precisa .returncode e .stderr).
    """
    runner = runner or (lambda cmd, **kw: subprocess.run(cmd, capture_output=True, text=True, **kw))

    cached = find_cached_track(game_name)
    if cached:
        logger.info("Usando faixa em cache para '%s': %s", game_name, cached)
        return cached

    manual = find_manual_track(game_name)
    if manual:
        logger.info("Usando faixa MANUAL fornecida pelo usuário para '%s': %s", game_name, manual)
        return _prepare_manual_track(manual, game_name, timeout, runner)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(game_name)
    raw_path = CACHE_DIR / f"{slug}_raw.m4a"
    final_path = CACHE_DIR / f"{slug}.mp3"

    query = f"ytsearch1:{game_name} official soundtrack main theme"
    section = f"*{CLIP_START_SECONDS}-{CLIP_START_SECONDS + CLIP_DURATION_SECONDS}"

    download_cmd = [
        "yt-dlp",
        query,
        "--js-runtimes",
        "deno",
        "-f",
        "bestaudio",
        "--download-sections",
        section,
        "-o",
        str(raw_path),
    ]

    try:
        result = runner(download_cmd, timeout=timeout)
    except Exception:
        logger.exception("Falha ao rodar yt-dlp (áudio) para '%s'", game_name)
        return None

    if result.returncode != 0 or not raw_path.exists():
        logger.warning(
            "yt-dlp não encontrou/baixou OST para '%s' (returncode=%s): %s. "
            "Se for restrição de idade, coloque uma faixa manual em "
            "video_gen/manual_music/%s.mp3",
            game_name,
            getattr(result, "returncode", "?"),
            getattr(result, "stderr", "")[-500:],
            slug,
        )
        return None

    # Converte para mp3 (formato consumido pelo Remotion/assembler).
    convert_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-t",
        str(CLIP_DURATION_SECONDS),
        str(final_path),
    ]
    convert_result = runner(convert_cmd, timeout=timeout)
    raw_path.unlink(missing_ok=True)

    if convert_result.returncode != 0 or not final_path.exists():
        logger.warning("Falha ao converter faixa de áudio para '%s'", game_name)
        return None

    logger.info("Faixa de música de fundo pronta para '%s': %s", game_name, final_path)
    return final_path
