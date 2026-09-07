"""Monta o vídeo: roteiro -> narração (TTS) -> legendas sincronizadas (whisper)
-> spec JSON consumido pelo template Remotion -> renderização (subprocess).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from video_gen.captions import transcribe_words
from video_gen.tts import synthesize_speech

logger = logging.getLogger("video_gen")

PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "video_gen" / "remotion"
REMOTION_PUBLIC_AUDIO_DIR = REMOTION_DIR / "public" / "audio"
OUTPUT_DIR = PROJECT_ROOT / "data" / "videos"
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"
SPECS_DIR = PROJECT_ROOT / "data" / "video_specs"


def build_narration_text(hook: str, body: str, cta: str) -> str:
    """Junta hook + body + cta em um único texto de narração."""
    return f"{hook} {body} {cta}".strip()


def build_video_spec(
    item_id: int,
    hook: str,
    body: str,
    cta: str,
    audio_relative_path: str,
    words: list,
    source: str,
    title: str,
) -> dict:
    """Monta o dicionário de spec do vídeo (o que o componente Remotion consome).

    `audio_relative_path` deve ser relativo à pasta public/ do projeto Remotion
    (ex: "audio/item_1.mp3"), consumido via staticFile() no componente.
    """
    return {
        "itemId": item_id,
        "title": title,
        "source": source,
        "hook": hook,
        "body": body,
        "cta": cta,
        "audioPath": audio_relative_path,
        "words": [w.to_dict() if hasattr(w, "to_dict") else w for w in words],
    }


def write_spec(spec: dict, item_id: int) -> Path:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    path = SPECS_DIR / f"item_{item_id}.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
    ]
    logger.info("Renderizando vídeo (item %s): %s", item_id, " ".join(cmd))

    result = subprocess.run(
        cmd, cwd=str(REMOTION_DIR), capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        logger.error("Falha ao renderizar item %s:\n%s", item_id, result.stderr[-4000:])
        raise RuntimeError(f"remotion render falhou (item {item_id}): {result.stderr[-500:]}")

    logger.info("Vídeo renderizado: %s", output_path)
    return output_path


def generate_video_for_item(row, render: bool = True) -> dict:
    """Pipeline completo para um item do banco (linha com script_hook/body/cta):
    TTS -> transcrição -> spec JSON -> (opcional) render Remotion.

    Retorna um dict com paths gerados. `render=False` permite gerar só o spec
    (útil em ambientes sem Node/Remotion configurado).
    """
    item_id = row["id"]
    hook, body, cta = row["script_hook"], row["script_body"], row["script_cta"]

    narration_text = build_narration_text(hook, body, cta)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = AUDIO_DIR / f"item_{item_id}.mp3"
    synthesize_speech(narration_text, audio_path)
    logger.info("Áudio gerado (item %s): %s", item_id, audio_path)

    words = transcribe_words(audio_path)
    logger.info("Transcrição: %d palavras (item %s)", len(words), item_id)

    # Remotion só serve assets estáticos de dentro de remotion/public/;
    # copiamos o áudio pra lá e referenciamos via caminho relativo (staticFile()).
    REMOTION_PUBLIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    public_audio_path = REMOTION_PUBLIC_AUDIO_DIR / audio_path.name
    shutil.copyfile(audio_path, public_audio_path)
    audio_relative_path = f"audio/{audio_path.name}"

    spec = build_video_spec(
        item_id=item_id,
        hook=hook,
        body=body,
        cta=cta,
        audio_relative_path=audio_relative_path,
        words=words,
        source=row["source"],
        title=row["title"],
    )
    spec_path = write_spec(spec, item_id)

    result = {"item_id": item_id, "audio_path": str(audio_path), "spec_path": str(spec_path)}

    if render:
        video_path = render_video(spec_path, item_id)
        result["video_path"] = str(video_path)

    return result
