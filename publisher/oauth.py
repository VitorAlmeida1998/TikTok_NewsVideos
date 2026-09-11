"""Fluxo OAuth2 da TikTok (Login Kit / Content Posting API).

Endpoints e parâmetros conferidos na documentação oficial em
developers.tiktok.com (doc/login-kit-web e doc/oauth-user-access-token-management):
- Autorização: GET https://www.tiktok.com/v2/auth/authorize/
- Troca de código / refresh: POST https://open.tiktokapis.com/v2/oauth/token/
- redirect_uri precisa ser absoluto e https (localhost não é aceito).
- access_token válido por 24h; refresh_token válido por 365 dias e é
  ROTACIONADO a cada renovação — sempre salvar o valor mais recente
  retornado, nunca reusar um refresh_token antigo depois de uma renovação
  bem-sucedida.
"""
from __future__ import annotations

from urllib.parse import urlencode

import requests

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


class OAuthError(RuntimeError):
    pass


def build_authorize_url(
    client_key: str, redirect_uri: str, scope: str = "video.upload", state: str = ""
) -> str:
    """Monta a URL de autorização pro usuário abrir no navegador e logar.

    `scope` aceita múltiplos valores separados por vírgula (ex:
    "video.upload,user.info.basic"). Use "video.upload" pro modo rascunho
    (mais seguro) ou "video.publish" pro modo de publicação direta (exige
    aprovação mais rigorosa da TikTok).
    """
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(
    code: str, client_key: str, client_secret: str, redirect_uri: str, session=None
) -> dict:
    """Troca o authorization code (obtido depois do login no navegador) pelo
    par inicial access_token/refresh_token. Só precisa rodar uma vez — depois
    disso, refresh_access_token cuida de renovar por até 365 dias.
    """
    session = session or requests
    resp = session.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    return _parse_token_response(resp, "troca de código")


def refresh_access_token(
    refresh_token: str, client_key: str, client_secret: str, session=None
) -> dict:
    """Usa o refresh_token pra obter um novo access_token (o atual dura só
    24h). A resposta pode trazer um refresh_token novo — o chamador deve
    sempre persistir o valor retornado aqui, não o que foi passado.
    """
    session = session or requests
    resp = session.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    return _parse_token_response(resp, "refresh de token")


def _parse_token_response(resp, step: str) -> dict:
    if resp.status_code != 200:
        raise OAuthError(f"Falha na {step} (status {resp.status_code}): {resp.text[:500]}")
    data = resp.json()
    if "access_token" not in data:
        raise OAuthError(f"Resposta sem access_token na {step}: {data}")
    return data
