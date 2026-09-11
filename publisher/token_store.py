"""Armazenamento local do par access_token/refresh_token do TikTok.

Guardado num JSON dedicado (fora do .env) porque o refresh_token é
ROTACIONADO a cada renovação — reescrever o .env programaticamente a cada
chamada seria mais frágil do que ler/escrever um arquivo de estado dedicado.
Nunca commitar esse arquivo (ver .gitignore) — tem o mesmo nível de
sensibilidade que uma senha.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DEFAULT_STORE_PATH = "data/tiktok_tokens.json"

# Margem de segurança antes do vencimento real do access_token, pra nunca
# tentar usar um token que expira no meio de uma chamada por causa de
# latência de rede ou pequena divergência de relógio.
EXPIRY_MARGIN_SECONDS = 300


def load_tokens(path: str | None = None) -> dict | None:
    """Lê o par de tokens salvo, ou None se ainda não existe (setup inicial
    via `publisher.get_token` não foi rodado)."""
    file_path = Path(path or DEFAULT_STORE_PATH)
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text(encoding="utf-8"))


def save_tokens(
    access_token: str,
    refresh_token: str,
    expires_in: int,
    path: str | None = None,
) -> None:
    file_path = Path(path or DEFAULT_STORE_PATH)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in - EXPIRY_MARGIN_SECONDS,
    }
    file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_expired(tokens: dict) -> bool:
    return time.time() >= tokens.get("expires_at", 0)
