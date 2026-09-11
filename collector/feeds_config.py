"""Leitura da configuração de feeds RSS a partir de feeds.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_FEEDS_PATH = "feeds.yaml"


@dataclass
class FeedConfig:
    name: str
    url: str


def load_feeds(path: str | Path = DEFAULT_FEEDS_PATH) -> list[FeedConfig]:
    """Carrega a lista de feeds configurados em um arquivo YAML.

    Formato esperado:
        feeds:
          - name: ign
            url: https://...
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de feeds não encontrado: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    entries = raw.get("feeds", [])
    feeds: list[FeedConfig] = []
    for entry in entries:
        if "name" not in entry or "url" not in entry:
            raise ValueError(f"Entrada de feed inválida (faltando name/url): {entry}")
        feeds.append(FeedConfig(name=entry["name"], url=entry["url"]))

    return feeds
