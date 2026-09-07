"""Testes do TTS (mock do cliente ElevenLabs, sem chamadas reais/custo)."""
from unittest.mock import MagicMock

from video_gen.tts import synthesize_speech


def test_synthesize_speech_writes_file(tmp_path):
    fake_client = MagicMock()
    fake_client.text_to_speech.convert.return_value = iter([b"chunk1", b"chunk2"])

    output_path = tmp_path / "audio" / "out.mp3"
    result = synthesize_speech("Olá mundo", output_path, client=fake_client)

    assert result == output_path
    assert output_path.exists()
    assert output_path.read_bytes() == b"chunk1chunk2"
    fake_client.text_to_speech.convert.assert_called_once()


def test_synthesize_speech_creates_parent_dirs(tmp_path):
    fake_client = MagicMock()
    fake_client.text_to_speech.convert.return_value = iter([b"data"])

    nested_path = tmp_path / "a" / "b" / "c" / "audio.mp3"
    synthesize_speech("Teste", nested_path, client=fake_client)

    assert nested_path.exists()
