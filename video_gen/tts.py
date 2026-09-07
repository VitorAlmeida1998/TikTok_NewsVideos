"""Text-to-speech via ElevenLabs: gera o áudio de narração a partir do roteiro."""
from __future__ import annotations

import os
from pathlib import Path

from elevenlabs import ElevenLabs

# Voz padrão ElevenLabs multilíngue (pt-BR funciona bem com o modelo multilingual).
# "Antoni"/"Bella" etc. variam por conta; usamos uma voz pública estável.
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam (multilingual v2)
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


def _get_client() -> ElevenLabs:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY não configurada. Defina no .env (veja .env.example)."
        )
    return ElevenLabs(api_key=api_key)


def synthesize_speech(
    text: str,
    output_path: str | Path,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = DEFAULT_MODEL_ID,
    client: ElevenLabs | None = None,
) -> Path:
    """Gera um arquivo de áudio MP3 a partir do texto e salva em `output_path`.

    `client` pode ser injetado para testes; se omitido, cria um cliente real
    usando ELEVENLABS_API_KEY do ambiente.
    """
    client = client or _get_client()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_stream = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id=model_id,
        text=text,
        output_format="mp3_44100_128",
    )

    with output_path.open("wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)

    return output_path
