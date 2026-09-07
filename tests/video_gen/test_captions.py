"""Testes da transcrição de legendas (mock do WhisperModel, sem custo/tempo de inferência)."""
from unittest.mock import MagicMock

from video_gen.captions import WordTiming, transcribe_words


def _make_mock_model(words_per_segment):
    fake_model = MagicMock()
    segments = []
    for words in words_per_segment:
        seg = MagicMock()
        seg.words = words
        segments.append(seg)
    fake_model.transcribe.return_value = (segments, MagicMock())
    return fake_model


def _make_word(word, start, end):
    w = MagicMock()
    w.word = word
    w.start = start
    w.end = end
    return w


def test_transcribe_words_flattens_segments():
    words_seg1 = [_make_word(" Olá", 0.0, 0.3), _make_word(" mundo", 0.3, 0.7)]
    words_seg2 = [_make_word(" tudo", 1.0, 1.3), _make_word(" bem", 1.3, 1.6)]
    model = _make_mock_model([words_seg1, words_seg2])

    result = transcribe_words("fake.mp3", model=model)

    assert len(result) == 4
    assert all(isinstance(w, WordTiming) for w in result)
    assert result[0].word == "Olá"  # strip aplicado
    assert result[0].start == 0.0
    assert result[3].word == "bem"


def test_transcribe_words_calls_model_with_word_timestamps():
    model = _make_mock_model([])
    transcribe_words("fake.mp3", language="pt", model=model)

    model.transcribe.assert_called_once_with(
        "fake.mp3", language="pt", word_timestamps=True
    )


def test_word_timing_to_dict():
    w = WordTiming(word="oi", start=0.0, end=0.5)
    assert w.to_dict() == {"word": "oi", "start": 0.0, "end": 0.5}
