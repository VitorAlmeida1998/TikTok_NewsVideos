"""Monta o vídeo: roteiro -> narração (TTS) -> legendas sincronizadas (whisper)
-> spec JSON consumido pelo template Remotion -> renderização (subprocess).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path

from shared.settings import load_settings
from video_gen.cover import render_cover
from video_gen.gameplay import download_trailer_clip
from video_gen.music import download_ost_clip
from video_gen.pronunciation import (
    load_pronunciations,
    merge_pronunciations,
    parse_pronunciation_field,
)
from video_gen.tts import synthesize_speech

logger = logging.getLogger("video_gen")


class MediaMissingError(RuntimeError):
    """Item pulado por falta de vídeo de fundo/música (modo require_media)."""

PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "video_gen" / "remotion"
REMOTION_PUBLIC_AUDIO_DIR = REMOTION_DIR / "public" / "audio"
REMOTION_PUBLIC_BACKGROUND_DIR = REMOTION_DIR / "public" / "background"
REMOTION_PUBLIC_MUSIC_DIR = REMOTION_DIR / "public" / "music"
OUTPUT_DIR = PROJECT_ROOT / "data" / "videos"
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"
SPECS_DIR = PROJECT_ROOT / "data" / "video_specs"


def build_narration_text(hook: str, body: str, cta: str) -> str:
    """Junta hook + body + cta em um único texto de narração."""
    return f"{hook} {body} {cta}".strip()


# Selo de canto exibido no vídeo (reconhecimento de marca + urgência), derivado
# das matched_keywords que o dedupe já salva pra cada item — sem precisar de
# nenhum campo novo gerado por IA. Ordem = prioridade quando mais de uma
# keyword bate (a mais "chamativa" primeiro).
BADGE_RULES: list[tuple[list[str], str]] = [
    (["leak", "leaked", "leaks"], "VAZOU"),
    (["exclusive"], "EXCLUSIVO"),
    (["delay", "delayed"], "ATRASOU"),
    (["confirmed", "confirms"], "CONFIRMADO"),
    (["reveal", "revealed", "reveals", "announce", "announced", "announces"], "REVELADO"),
    (["release date"], "DATA CONFIRMADA"),
    (["trailer"], "TRAILER"),
]


def derive_badge(matched_keywords: str | None) -> str:
    """Deriva o texto do selo de canto a partir da string de keywords batidas
    (formato "kw1,kw2,...", salvo pelo dedupe). String vazia = sem selo.
    """
    if not matched_keywords:
        return ""
    matched = set(matched_keywords.split(","))
    for keywords, badge in BADGE_RULES:
        if matched & set(keywords):
            return badge
    return ""


def build_video_spec(
    item_id: int,
    hook: str,
    body: str,
    cta: str,
    audio_relative_path: str,
    words: list,
    source: str,
    title: str,
    background_relative_path: str = "",
    music_relative_path: str = "",
    badge: str = "",
    game_name: str = "",
) -> dict:
    """Monta o dicionário de spec do vídeo (o que o componente Remotion consome).

    `audio_relative_path`, `background_relative_path` e `music_relative_path`
    devem ser relativos à pasta public/ do projeto Remotion (ex:
    "audio/item_1.mp3", "background/forza-horizon-6.mp4",
    "music/forza-horizon-6.mp3"), consumidos via staticFile() no componente.
    Vazio = sem fundo de gameplay / sem música, respectivamente. `badge` é o
    selo de canto (ex: "VAZOU", "CONFIRMADO") — vazio = sem selo.
    """
    settings = load_settings()
    return {
        "itemId": item_id,
        "title": title,
        "source": source,
        "hook": hook,
        "body": body,
        "cta": cta,
        "audioPath": audio_relative_path,
        "backgroundVideoPath": background_relative_path,
        "musicPath": music_relative_path,
        "badge": badge,
        # usado só pela capa (NewsCover); o NewsShort ignora
        "gameName": game_name,
        # marca do canal vinda de data/settings.json: trocar o nome do canal
        # não exige mexer no template Remotion
        "channelHandle": settings.get("channel_handle", ""),
        "channelInitials": settings.get("channel_initials", ""),
        "words": [w.to_dict() if hasattr(w, "to_dict") else w for w in words],
    }


def write_spec(spec: dict, item_id: int) -> Path:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    path = SPECS_DIR / f"item_{item_id}.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# Fora de um terminal, o `remotion render` imprime o progresso linha a linha
# ("Bundling 62%", "Rendered 120/862, time remaining: ..."). Lemos isso ao vivo
# e reemitimos como log a cada 10% — sem isso o painel fica ~85s parado, sem
# nenhum sinal de que algo está acontecendo.
_RENDER_PROGRESS = re.compile(r"Rendered (\d+)/(\d+)")
_PROGRESS_STEP = 10  # em pontos percentuais


def _stream_subprocess(cmd: list[str], cwd: str, timeout: int, on_line) -> tuple[int, str]:
    """Roda o comando repassando cada linha de saída para `on_line`.

    stderr vai junto do stdout (uma leitura só, sem risco de travar com o
    buffer do outro cheio). Devolve (returncode, últimas linhas), usadas na
    mensagem de erro quando falha.
    """
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    # o timeout do subprocess.run some ao usar Popen; um watchdog garante que
    # um render travado não segure o pipeline pra sempre
    watchdog = threading.Timer(timeout, process.kill)
    watchdog.start()
    tail: deque[str] = deque(maxlen=40)
    try:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            tail.append(line)
            on_line(line)
        returncode = process.wait()
    finally:
        watchdog.cancel()
        if process.poll() is None:
            process.kill()
    return returncode, "\n".join(tail)


def _progress_reporter(item_id: int):
    """Reemite o progresso do Remotion como log, a cada 10%."""
    state = {"last_bucket": -1}

    def on_line(line: str) -> None:
        match = _RENDER_PROGRESS.search(line)
        if not match:
            return
        done, total = int(match.group(1)), int(match.group(2))
        if not total:
            return
        percent = done * 100 // total
        bucket = percent // _PROGRESS_STEP
        if bucket > state["last_bucket"]:
            state["last_bucket"] = bucket
            logger.info("Render do item %s: %d%% (%d/%d frames)", item_id, percent, done, total)

    return on_line


def render_video(spec_path: Path, item_id: int, timeout: int = 600) -> Path:
    """Chama `npx remotion render` no projeto Remotion, passando o spec como props.

    Requer Node.js/npm instalados e dependências do projeto Remotion
    instaladas (`npm install` dentro de video_gen/remotion).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"item_{item_id}.mp4"

    cmd = [
        "npx",
        "remotion",
        "render",
        "NewsShort",
        str(output_path),
        f"--props={spec_path}",
        # CRF 16 (padrão do Remotion é 18): dá pro TikTok recomprimir a
        # partir de uma fonte mais próxima de sem perdas, já que a etapa
        # de upload SEMPRE recodifica o vídeo de novo do lado deles — quanto
        # melhor a fonte, menos artefato acumulado na segunda passada.
        "--crf=16",
        # --color-space=bt709 força "-color_range tv" e a conversão de faixa
        # de cor completa (full-range) pra limitada (tv-range) no ffmpeg.
        # Sem isso, o Remotion (que renderiza a partir de um canvas de
        # Chromium, que é full-range) gera yuvj420p em vez de yuv420p — o
        # TikTok e a maioria dos players reinterpretam isso com a faixa
        # errada, o que dessatura levemente as cores/contraste do vídeo.
        "--color-space=bt709",
    ]
    logger.info("Renderizando vídeo (item %s): %s", item_id, " ".join(cmd))

    returncode, output_tail = _stream_subprocess(
        cmd, cwd=str(REMOTION_DIR), timeout=timeout, on_line=_progress_reporter(item_id)
    )
    if returncode != 0:
        logger.error("Falha ao renderizar item %s:\n%s", item_id, output_tail[-4000:])
        raise RuntimeError(f"remotion render falhou (item {item_id}): {output_tail[-500:]}")

    logger.info("Vídeo renderizado: %s", output_path)
    return output_path


def _publish_asset(src: Path, public_dir: Path, prefix: str) -> str:
    """Copia um asset pra dentro de remotion/public/ (Remotion só serve assets
    de lá, via staticFile()) e devolve o caminho relativo pro spec."""
    public_dir.mkdir(parents=True, exist_ok=True)
    dest = public_dir / src.name
    if not dest.exists():
        shutil.copyfile(src, dest)
    return f"{prefix}/{src.name}"


def resolve_media(game_name: str | None) -> tuple[Path | None, Path | None]:
    """Fundo de gameplay (trailer oficial) e música (OST) do jogo, via cache /
    clipe manual / yt-dlp. Qualquer um pode vir None. Uso de OST oficial é
    decisão explícita do usuário (risco de copyright no TikTok assumido);
    nunca contorna verificação de idade/login do YouTube."""
    if not game_name:
        return None, None
    return download_trailer_clip(game_name), download_ost_clip(game_name)


def _row_get(row, key: str):
    return row[key] if key in row.keys() else None


def generate_video_for_item(row, render: bool = True, require_media: bool = False) -> dict:
    """Pipeline completo para um item do banco (linha com script_hook/body/cta):
    mídia de fundo -> TTS (com timestamps por palavra) -> spec JSON ->
    (opcional) render Remotion.

    `require_media=True` (modo autônomo) levanta MediaMissingError ANTES de
    gastar créditos de TTS se o item não tiver jogo identificado, vídeo de
    fundo ou música. Com False, cai no fundo gradiente / sem música.
    `render=False` gera só o spec (útil sem Node/Remotion).
    """
    item_id = row["id"]
    hook, body, cta = row["script_hook"], row["script_body"], row["script_cta"]
    game_name = _row_get(row, "game_name")

    clip_path, track_path = resolve_media(game_name)
    if require_media:
        if not game_name:
            raise MediaMissingError("sem nome de jogo identificado no roteiro")
        missing = [
            label
            for label, present in (("vídeo de fundo", clip_path), ("música", track_path))
            if not present
        ]
        if missing:
            raise MediaMissingError(f"sem {' e '.join(missing)} para '{game_name}'")

    background_relative_path = ""
    if clip_path:
        background_relative_path = _publish_asset(
            clip_path, REMOTION_PUBLIC_BACKGROUND_DIR, "background"
        )
    elif game_name:
        logger.info("Sem clipe de gameplay para '%s' (item %s), usando fundo padrão", game_name, item_id)

    music_relative_path = ""
    if track_path:
        music_relative_path = _publish_asset(track_path, REMOTION_PUBLIC_MUSIC_DIR, "music")
    elif game_name:
        logger.info("Sem música de fundo para '%s' (item %s), só narração", game_name, item_id)

    pronunciations = merge_pronunciations(
        load_pronunciations(), parse_pronunciation_field(_row_get(row, "script_pronunciations"))
    )
    narration_text = build_narration_text(hook, body, cta)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    speech = synthesize_speech(
        narration_text, AUDIO_DIR / f"item_{item_id}.mp3", pronunciations=pronunciations
    )
    audio_path = speech.audio_path
    words = speech.words
    logger.info("Áudio gerado (item %s): %s — %d palavras alinhadas", item_id, audio_path, len(words))
    if speech.spoken_text != narration_text:
        logger.info("Texto falado com respelling (item %s): %s", item_id, speech.spoken_text)

    audio_relative_path = _publish_asset(audio_path, REMOTION_PUBLIC_AUDIO_DIR, "audio")

    matched_keywords = _row_get(row, "matched_keywords")
    spec = build_video_spec(
        item_id=item_id,
        hook=hook,
        body=body,
        cta=cta,
        audio_relative_path=audio_relative_path,
        words=words,
        source=row["source"],
        title=row["title"],
        background_relative_path=background_relative_path,
        music_relative_path=music_relative_path,
        badge=derive_badge(matched_keywords),
        game_name=game_name or "",
    )
    spec_path = write_spec(spec, item_id)

    result = {"item_id": item_id, "audio_path": str(audio_path), "spec_path": str(spec_path)}

    if render:
        video_path = render_video(spec_path, item_id)
        result["video_path"] = str(video_path)

        # Capa pro TikTok (grade do perfil/busca). Nunca pode derrubar o
        # vídeo: se falhar, o item segue publicável, só sem capa própria.
        try:
            result["cover_path"] = str(render_cover(spec_path, item_id))
        except Exception:
            logger.warning("Falha ao gerar capa do item %s (vídeo segue válido)", item_id, exc_info=True)

    return result
