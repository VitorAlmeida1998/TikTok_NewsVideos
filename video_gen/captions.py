"""Geração de legendas sincronizadas por palavra via faster-whisper (local, offline).

Transcreve o áudio de narração já gerado (video_gen/tts.py) e retorna uma
lista de palavras com timestamps (início/fim em segundos), usada para
alimentar as legendas animadas no template Remotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

DEFAULT_MODEL_SIZE = "base"  # bom equilíbrio velocidade/qualidade em CPU


@dataclass
class WordTiming:
    word: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"word": self.word, "start": self.start, "end": self.end}


_model_cache: dict[str, WhisperModel] = {}


def _get_model(model_size: str = DEFAULT_MODEL_SIZE) -> WhisperModel:
    if model_size not in _model_cache:
        _model_cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[model_size]


def transcribe_words(
    audio_path: str | Path,
    language: str = "pt",
    model_size: str = DEFAULT_MODEL_SIZE,
    model: WhisperModel | None = None,
) -> list[WordTiming]:
    """Transcreve o áudio e retorna timestamps por palavra.

    `model` pode ser injetado para testes (mock); se omitido, usa/instancia
    um WhisperModel real (cacheado em processo).
    """
    model = model or _get_model(model_size)

    segments, _info = model.transcribe(
        str(audio_path), language=language, word_timestamps=True
    )

    words: list[WordTiming] = []
    for segment in segments:
        for w in segment.words or []:
            words.append(WordTiming(word=w.word.strip(), start=w.start, end=w.end))

    return words
