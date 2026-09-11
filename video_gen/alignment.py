"""Converte o alinhamento por caractere do ElevenLabs em timestamps por
palavra exibida (legenda), usando os spans calculados em pronunciation.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from video_gen.pronunciation import WordSpan


@dataclass
class WordTiming:
    word: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"word": self.word, "start": self.start, "end": self.end}


def word_timings_from_alignment(
    spans: list[WordSpan],
    characters: list[str],
    start_times: list[float],
    end_times: list[float],
) -> list[WordTiming]:
    """Pra cada span [start, end) no texto falado, pega o primeiro início e o
    último fim entre os caracteres não-espaço daquele intervalo.

    Palavras que caírem fora do alinhamento (não deveria acontecer, o
    alinhamento cobre o texto inteiro) herdam o fim da palavra anterior.
    """
    timings: list[WordTiming] = []
    last_end = 0.0
    total = min(len(characters), len(start_times), len(end_times))

    for span in spans:
        start = None
        end = None
        for idx in range(max(0, span.start), min(span.end, total)):
            if characters[idx].isspace():
                continue
            start = start_times[idx] if start is None else min(start, start_times[idx])
            end = end_times[idx] if end is None else max(end, end_times[idx])

        if start is None or end is None:
            start = end = last_end
        start = max(start, last_end) if timings else start
        end = max(end, start)
        timings.append(WordTiming(word=span.word, start=round(start, 3), end=round(end, 3)))
        last_end = end

    return timings
