"""Testes do TTS (mock do cliente ElevenLabs, sem chamadas reais/custo)."""
import base64
from unittest.mock import MagicMock

from video_gen.tts import synthesize_speech


def _fake_client(spoken_text_holder: dict):
    """Cliente falso: devolve áudio fixo e um alinhamento uniforme (0.1s por
    caractere) do texto que recebeu — o que o ElevenLabs faz de verdade."""
    client = MagicMock()

    def convert_with_timestamps(**kwargs):
        text = kwargs["text"]
        spoken_text_holder["text"] = text
        response = MagicMock()
        response.audio_base_64 = base64.b64encode(b"audio-bytes").decode()
        response.alignment.characters = list(text)
        response.alignment.character_start_times_seconds = [i * 0.1 for i in range(len(text))]
        response.alignment.character_end_times_seconds = [(i + 1) * 0.1 for i in range(len(text))]
        return response

    client.text_to_speech.convert_with_timestamps.side_effect = convert_with_timestamps
    return client


def test_synthesize_speech_writes_file_and_returns_word_timings(tmp_path):
    holder = {}
    output_path = tmp_path / "audio" / "out.mp3"

    result = synthesize_speech("Olá mundo!", output_path, client=_fake_client(holder))

    assert result.audio_path == output_path
    assert output_path.read_bytes() == b"audio-bytes"
    assert [w.word for w in result.words] == ["Olá", "mundo!"]
    assert result.words[0].start == 0.0
    assert result.words[0].end == 0.3  # "Olá" = chars 0..2
    assert result.words[1].start == 0.4  # após o espaço
    assert result.words[1].end == 1.0


def test_synthesize_speech_applies_pronunciations_only_to_spoken_text(tmp_path):
    holder = {}
    result = synthesize_speech(
        "Wolverine vazou hoje",
        tmp_path / "a.mp3",
        pronunciations={"wolverine": "Uólverin"},
        client=_fake_client(holder),
    )

    assert holder["text"] == "Uólverin vazou hoje"
    assert result.spoken_text == "Uólverin vazou hoje"
    # legenda mantém a palavra original, com o tempo do respelling falado
    assert result.words[0].word == "Wolverine"
    assert result.words[0].end == len("Uólverin") * 0.1


def test_synthesize_speech_creates_parent_dirs(tmp_path):
    nested_path = tmp_path / "a" / "b" / "c" / "audio.mp3"
    synthesize_speech("Teste", nested_path, client=_fake_client({}))
    assert nested_path.exists()
