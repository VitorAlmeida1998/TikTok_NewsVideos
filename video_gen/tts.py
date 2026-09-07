"""Text-to-speech via ElevenLabs: gera o áudio de narração a partir do roteiro."""
from __future__ import annotations

import os
from pathlib import Path

from elevenlabs import ElevenLabs, VoiceSettings

# Voz padrão ElevenLabs multilíngue (pt-BR funciona bem com o modelo multilingual).
# Pode ser sobrescrita via env var ELEVENLABS_VOICE_ID (ex: pra testar outra
# voz mais jovem/enérgica sem mexer em código).
DEFAULT_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# Settings ajustados pra soar mais empolgado/expressivo (menos "robótico"):
# - stability baixa = mais variação emocional entre frases (voz "viva")
# - style alto = amplifica a expressividade/exagero natural da voz
# - speed levemente acima de 1.0 = ritmo mais rápido, energia de criador de
#   conteúdo em vez de narração pausada de telejornal
DEFAULT_VOICE_SETTINGS = VoiceSettings(
    stability=0.3,
    similarity_boost=0.8,
    style=0.65,
    use_speaker_boost=True,
    speed=1.08,
)


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
    voice_settings: VoiceSettings | None = None,
    client: ElevenLabs | None = None,
) -> Path:
    """Gera um arquivo de áudio MP3 a partir do texto e salva em `output_path`.

    `client` pode ser injetado para testes; se omitido, cria um cliente real
    usando ELEVENLABS_API_KEY do ambiente. `voice_settings` permite ajustar
    expressividade/velocidade; se omitido, usa DEFAULT_VOICE_SETTINGS
    (tunado pra soar empolgado).
    """
    client = client or _get_client()
    voice_settings = voice_settings or DEFAULT_VOICE_SETTINGS
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_stream = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id=model_id,
        text=text,
        voice_settings=voice_settings,
        output_format="mp3_44100_128",
    )

    with output_path.open("wb") as f:
        for chunk in audio_stream:
            if chunk:
                f.write(chunk)

    return output_path
