"""Cache de ETag/Last-Modified por feed, para GET condicional.

Guardado em data/feed_cache.json. É só otimização: apagar o arquivo faz o
collector baixar tudo de novo na próxima rodada, sem perder nada (o dedupe
por content_hash impede duplicata no banco).
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_PATH = PROJECT_ROOT / "data" / "feed_cache.json"


def load_cache(path: Path = CACHE_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache: dict[str, dict], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
