"""Guarda de créditos do ElevenLabs.

O plano do usuário é por caracteres/mês (Starter = 30k, ~82 narrações). Como
o monitor roda sozinho e a fila de notícias é sempre maior que a cota, sem
uma trava ele queima o mês inteiro numa tarde — e aí nenhum vídeo sai até a
renovação. Antes de sintetizar, o pipeline pergunta quantos caracteres ainda
restam e para enquanto ainda há reserva.

Se a chave não tiver permissão de ler a assinatura, `remaining_characters`
devolve None e o pipeline segue normalmente (guarda é best-effort, nunca
bloqueia por erro de leitura).
"""
from __future__ import annotations

import logging

from elevenlabs import ElevenLabs

logger = logging.getLogger("video_gen.quota")


def remaining_characters(client: ElevenLabs | None = None) -> int | None:
    """Caracteres ainda disponíveis no ciclo atual, ou None se não der pra ler."""
    try:
        client = client or ElevenLabs()
        subscription = client.user.subscription.get()
        return max(0, subscription.character_limit - subscription.character_count)
    except Exception as exc:  # permissão, rede, mudança de API...
        logger.debug("Não foi possível ler a cota do ElevenLabs: %s", exc)
        return None


def has_budget_for(text_length: int, reserve: int, client: ElevenLabs | None = None) -> bool:
    """True se cabe sintetizar `text_length` caracteres mantendo `reserve`
    de folga (ou se a cota não pôde ser lida)."""
    remaining = remaining_characters(client)
    if remaining is None:
        return True
    if remaining - text_length < reserve:
        logger.warning(
            "Cota do ElevenLabs quase no fim: restam %d caracteres (reserva %d) — "
            "pulando geração até a renovação do plano",
            remaining,
            reserve,
        )
        return False
    return True
