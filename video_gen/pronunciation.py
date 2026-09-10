"""Respelling fonético de termos em inglês para o TTS falar do jeito que um
criador brasileiro fala ("Wolverine" -> "Uólverin"), sem trocar o texto
exibido nas legendas.

Duas fontes de aliases, mescladas (a global vence):
1. `pronunciations.yaml` na raiz do projeto — curado pelo usuário, vale pra
   todos os vídeos.
2. Campo PRONUNCIATIONS gerado pelo script_gen por notícia (formato
   "termo=respelling; outro=respelling"), salvo em script_pronunciations.

`build_spoken_text` devolve o texto falado e, pra cada palavra exibida, o
intervalo de caracteres correspondente no texto falado — é isso que permite
mapear o alinhamento por caractere do ElevenLabs de volta pras palavras
originais das legendas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PRONUNCIATIONS_PATH = PROJECT_ROOT / "pronunciations.yaml"

_EDGE_PUNCT = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


@dataclass
class WordSpan:
    word: str
    start: int
    end: int


def load_pronunciations(path: str | Path = DEFAULT_PRONUNCIATIONS_PATH) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k).strip(): str(v).strip() for k, v in data.items() if str(v).strip()}


def parse_pronunciation_field(text: str | None) -> dict[str, str]:
    """Parseia "Wolverine=Uólverin; Stronghold=Strong-rôld" (saída do script_gen)."""
    result: dict[str, str] = {}
    if not text:
        return result
    for chunk in re.split(r"[;\n]", text):
        if "=" not in chunk:
            continue
        term, spoken = chunk.split("=", 1)
        term, spoken = term.strip(), spoken.strip()
        if term and spoken:
            result[term] = spoken
    return result


def merge_pronunciations(*sources: dict[str, str]) -> dict[str, str]:
    """Mescla dicionários; o PRIMEIRO argumento tem prioridade em caso de conflito."""
    merged: dict[str, str] = {}
    for source in reversed(sources):
        merged.update({k.lower(): v for k, v in source.items()})
    return merged


def _core(token: str) -> str:
    return _EDGE_PUNCT.sub("", token).lower()


def _split_edges(token: str) -> tuple[str, str, str]:
    """Separa pontuação inicial/final do miolo da palavra: "hoje!" -> ("", "hoje", "!")."""
    match = re.match(r"^([^\w]*)(.*?)([^\w]*)$", token, re.UNICODE)
    return match.group(1), match.group(2), match.group(3)


def build_spoken_text(text: str, aliases: dict[str, str] | None) -> tuple[str, list[WordSpan]]:
    """Aplica os aliases (case-insensitive, palavra inteira, frases de várias
    palavras aceitas) e devolve (texto_falado, spans por palavra exibida).

    Quando um alias cobre várias palavras exibidas, o trecho substituído é
    repartido proporcionalmente entre elas, pra cada uma continuar com um
    intervalo de tempo próprio na legenda.
    """
    tokens = text.split()
    aliases = {k.lower(): v for k, v in (aliases or {}).items()}
    phrases = sorted(
        ((tuple(k.split()), v) for k, v in aliases.items()), key=lambda kv: -len(kv[0])
    )

    pieces: list[str] = []
    spans: list[WordSpan] = []
    cursor = 0
    i = 0
    while i < len(tokens):
        replacement = None
        length = 1
        for phrase, spoken in phrases:
            n = len(phrase)
            if i + n <= len(tokens) and tuple(_core(t) for t in tokens[i : i + n]) == phrase:
                replacement, length = spoken, n
                break

        if pieces:
            pieces.append(" ")
            cursor += 1

        if replacement is None:
            token = tokens[i]
            pieces.append(token)
            spans.append(WordSpan(token, cursor, cursor + len(token)))
            cursor += len(token)
            i += 1
            continue

        group = tokens[i : i + length]
        lead, _, _ = _split_edges(group[0])
        _, _, trail = _split_edges(group[-1])
        spoken_full = f"{lead}{replacement}{trail}"
        pieces.append(spoken_full)

        total_core = sum(len(_core(t)) or 1 for t in group)
        inner_start = cursor + len(lead)
        inner_len = len(replacement)
        offset = 0
        for idx, token in enumerate(group):
            share = (len(_core(token)) or 1) / total_core
            part_len = inner_len - offset if idx == length - 1 else max(1, round(inner_len * share))
            start = inner_start + offset
            end = start + part_len
            if idx == 0:
                start = cursor
            if idx == length - 1:
                end = cursor + len(spoken_full)
            spans.append(WordSpan(token, start, end))
            offset += part_len
        cursor += len(spoken_full)
        i += length

    return "".join(pieces), spans
