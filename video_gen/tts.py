"""Text-to-speech via ElevenLabs: gera o áudio de narração a partir do roteiro
e devolve também os timestamps por palavra (alinhamento por caractere do
próprio ElevenLabs — mais preciso que transcrever de volta com whisper, e as
legendas ficam com o texto exato do roteiro, sem erro de transcrição).
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from elevenlabs import ElevenLabs, VoiceSettings

from shared.settings import get_voice_id
from video_gen.alignment import WordTiming, word_timings_from_alignment
from video_gen.pronunciation import build_spoken_text

# A voz vem das configurações do painel (data/settings.json), caindo para
# ELEVENLABS_VOICE_ID do .env e, por último, para a voz padrão histórica.
# Resolvida por chamada (e não no import) pra troca de voz no painel valer
# no próximo vídeo sem reiniciar o processo.
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


@dataclass
class SpeechResult:
    audio_path: Path
    words: list[WordTiming]
    spoken_text: str


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
    voice_id: str | None = None,
    model_id: str = DEFAULT_MODEL_ID,
    voice_settings: VoiceSettings | None = None,
    pronunciations: dict[str, str] | None = None,
    client: ElevenLabs | None = None,
) -> SpeechResult:
    """Gera o MP3 da narração em `output_path` e devolve os timestamps por
    palavra do texto ORIGINAL (`text`), mesmo que `pronunciations` tenha
    trocado termos pelo respelling fonético no texto enviado ao TTS.

    `client` pode ser injetado para testes.
    """
    client = client or _get_client()
    voice_id = voice_id or get_voice_id()
    voice_settings = voice_settings or DEFAULT_VOICE_SETTINGS
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    spoken_text, spans = build_spoken_text(text, pronunciations)

    response = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        model_id=model_id,
        text=spoken_text,
        voice_settings=voice_settings,
        output_format="mp3_44100_128",
    )

    output_path.write_bytes(base64.b64decode(response.audio_base_64))

    alignment = response.alignment
    words = word_timings_from_alignment(
        spans,
        alignment.characters,
        alignment.character_start_times_seconds,
        alignment.character_end_times_seconds,
    )
    return SpeechResult(audio_path=output_path, words=words, spoken_text=spoken_text)
