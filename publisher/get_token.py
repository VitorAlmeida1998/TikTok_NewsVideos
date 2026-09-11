"""Setup único: troca o authorization code (obtido logando no navegador) pelo
par inicial access_token/refresh_token, e salva em data/tiktok_tokens.json.

Depois desse passo único, publisher/tiktok_client.py renova o access_token
sozinho via refresh_token (válido por 365 dias) — não precisa rodar isso de
novo até o refresh_token expirar ou ser revogado.

Pré-requisitos no .env:
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET — do app criado em
        developers.tiktok.com
    TIKTOK_REDIRECT_URI — precisa ser https e bater exatamente com o
        registrado no app (localhost não é aceito pela TikTok)
    TIKTOK_SCOPE (opcional) — default "video.upload" (modo rascunho/inbox,
        mais seguro). Use "video.publish" só se o app tiver esse escopo
        aprovado pra publicação direta.

Uso:
    uv run python -m publisher.get_token
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from publisher.oauth import OAuthError, build_authorize_url, exchange_code_for_token
from publisher.token_store import save_tokens

DEFAULT_SCOPE = "video.upload"


def main() -> None:
    load_dotenv()

    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    redirect_uri = os.environ.get("TIKTOK_REDIRECT_URI")

    missing = [
        name
        for name, val in (
            ("TIKTOK_CLIENT_KEY", client_key),
            ("TIKTOK_CLIENT_SECRET", client_secret),
            ("TIKTOK_REDIRECT_URI", redirect_uri),
        )
        if not val
    ]
    if missing:
        print(f"Faltando no .env: {', '.join(missing)}. Veja .env.example.")
        sys.exit(1)

    scope = os.environ.get("TIKTOK_SCOPE", DEFAULT_SCOPE)
    url = build_authorize_url(client_key, redirect_uri, scope=scope)

    print("1. Abra esse link no navegador, logado com a conta do TikTok que vai postar:\n")
    print(f"   {url}\n")
    print("2. Depois de autorizar, você cai no seu redirect_uri com ?code=... na URL.")
    print("   Copie só o valor do parâmetro 'code' (ele expira em poucos minutos).\n")
    code = input("Cole o 'code' aqui: ").strip()

    try:
        token_data = exchange_code_for_token(code, client_key, client_secret, redirect_uri)
    except OAuthError as exc:
        print(f"Erro ao trocar o código por token: {exc}")
        sys.exit(1)

    save_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_in=token_data.get("expires_in", 86400),
    )
    print("\nTokens salvos em data/tiktok_tokens.json — o publisher já pode ser usado.")


if __name__ == "__main__":
    main()
