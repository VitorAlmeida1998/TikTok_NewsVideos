"""Integração com a TikTok Content Posting API (v2, open.tiktokapis.com).

Requer um app registrado em https://developers.tiktok.com com o produto
"Content Posting API" aprovado, e um access_token OAuth2 do usuário com o
escopo `video.upload` (modo draft/inbox) e/ou `video.publish` (direct post).

Fluxo de upload (FILE_UPLOAD, vídeo local):
1. POST .../video/init/  -> retorna publish_id + upload_url
2. PUT <upload_url> com o vídeo em um único chunk (Content-Range) -> TikTok processa
3. (opcional) GET .../status/fetch/ para acompanhar o processamento

Dois modos:
- post_video_to_inbox(): envia como RASCUNHO — aparece na caixa de entrada
  do TikTok do usuário, que revisa e publica manualmente no app. Mais seguro,
  usado por padrão.
- post_video_direct(): publica diretamente no perfil (requer app com escopo
  video.publish aprovado pelo TikTok — sujeito a revisão mais rigorosa).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

logger = logging.getLogger("publisher")

API_BASE = "https://open.tiktokapis.com/v2"
INBOX_INIT_URL = f"{API_BASE}/post/publish/inbox/video/init/"
DIRECT_INIT_URL = f"{API_BASE}/post/publish/video/init/"
STATUS_URL = f"{API_BASE}/post/publish/status/fetch/"


class PublisherError(RuntimeError):
    pass


def _get_access_token() -> str:
    token = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise PublisherError(
            "TIKTOK_ACCESS_TOKEN não configurado. Defina no .env (veja .env.example). "
            "Requer app aprovado em developers.tiktok.com com Content Posting API."
        )
    return token


def _auth_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def post_video_to_inbox(
    video_path: str | Path,
    access_token: str | None = None,
    session=None,
) -> dict:
    """Envia um vídeo como rascunho para a caixa de entrada do TikTok do usuário
    (modo Inbox/Draft — o usuário revisa e publica manualmente no app).

    Retorna o dict de resposta do endpoint /video/init/ (contém publish_id).
    """
    access_token = access_token or _get_access_token()
    session = session or requests

    video_path = Path(video_path)
    if not video_path.exists():
        raise PublisherError(f"Arquivo de vídeo não encontrado: {video_path}")

    video_size = video_path.stat().st_size

    init_body = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        }
    }

    init_resp = session.post(
        INBOX_INIT_URL, headers=_auth_headers(access_token), json=init_body, timeout=30
    )
    _raise_for_tiktok_error(init_resp, "inbox/video/init")
    init_data = init_resp.json()

    upload_url = init_data["data"]["upload_url"]
    publish_id = init_data["data"]["publish_id"]

    _upload_video_bytes(video_path, upload_url, video_size, session=session)

    logger.info("Vídeo enviado para inbox do TikTok (publish_id=%s)", publish_id)
    return init_data


def post_video_direct(
    video_path: str | Path,
    title: str,
    privacy_level: str = "SELF_ONLY",
    access_token: str | None = None,
    session=None,
) -> dict:
    """Publica um vídeo diretamente no perfil do TikTok (Direct Post).

    `privacy_level`: SELF_ONLY (recomendado para testes/sandbox),
    PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, FOLLOWER_OF_CREATOR.
    Requer app com escopo `video.publish` aprovado pelo TikTok.

    Retorna o dict de resposta do endpoint /video/init/ (contém publish_id).
    """
    access_token = access_token or _get_access_token()
    session = session or requests

    video_path = Path(video_path)
    if not video_path.exists():
        raise PublisherError(f"Arquivo de vídeo não encontrado: {video_path}")

    video_size = video_path.stat().st_size

    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    init_resp = session.post(
        DIRECT_INIT_URL, headers=_auth_headers(access_token), json=init_body, timeout=30
    )
    _raise_for_tiktok_error(init_resp, "video/init (direct post)")
    init_data = init_resp.json()

    upload_url = init_data["data"]["upload_url"]
    publish_id = init_data["data"]["publish_id"]

    _upload_video_bytes(video_path, upload_url, video_size, session=session)

    logger.info("Vídeo publicado diretamente no TikTok (publish_id=%s)", publish_id)
    return init_data


def check_publish_status(
    publish_id: str, access_token: str | None = None, session=None
) -> dict:
    """Consulta o status de processamento/publicação de um vídeo enviado."""
    access_token = access_token or _get_access_token()
    session = session or requests

    resp = session.post(
        STATUS_URL,
        headers=_auth_headers(access_token),
        json={"publish_id": publish_id},
        timeout=30,
    )
    _raise_for_tiktok_error(resp, "status/fetch")
    return resp.json()


def _upload_video_bytes(video_path: Path, upload_url: str, video_size: int, session) -> None:
    """Faz o PUT do vídeo (chunk único) para a upload_url retornada pelo /init/."""
    with video_path.open("rb") as f:
        video_bytes = f.read()

    headers = {
        "Content-Type": "video/mp4",
        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
    }
    put_resp = session.put(upload_url, headers=headers, data=video_bytes, timeout=120)
    if put_resp.status_code not in (200, 201, 206):
        raise PublisherError(
            f"Falha ao enviar bytes do vídeo (status {put_resp.status_code}): "
            f"{put_resp.text[:500]}"
        )


def _raise_for_tiktok_error(resp, step: str) -> None:
    if resp.status_code != 200:
        raise PublisherError(f"TikTok API erro em {step} (status {resp.status_code}): {resp.text[:500]}")

    data = resp.json()
    error = data.get("error", {})
    if error.get("code") not in (None, "ok"):
        raise PublisherError(f"TikTok API erro em {step}: {error}")
