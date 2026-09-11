"""Ponto de entrada do módulo video_gen: gera vídeo (TTS + legendas + render)
para itens que já têm roteiro pronto, mais relevantes primeiro.

Uso:
    uv run python -m video_gen.run [--db data/news.db] [--limit N] [--no-render]
                                   [--require-media] [--max-age-hours H]

Requer ELEVENLABS_API_KEY no ambiente (.env). `--no-render` gera apenas o
áudio + spec JSON, sem chamar o Remotion. `--require-media` (modo autônomo)
pula — sem gastar TTS — itens sem vídeo de fundo ou música, marcando o motivo
no banco pra aparecerem como "aguardando mídia" no painel.
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from publisher.schedule import start_of_day
from shared.db import (
    count_videos_generated_since,
    get_connection,
    get_items_pending_video,
    save_video,
    set_video_skip_reason,
)
from video_gen.assembler import MediaMissingError, build_narration_text, generate_video_for_item
from video_gen.quota import has_budget_for

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("video_gen")


def run(
    db_path: str | None = None,
    limit: int | None = None,
    render: bool = True,
    require_media: bool = False,
    max_age_hours: float | None = None,
    daily_limit: int | None = None,
    tts_reserve_chars: int = 0,
    min_score: float = 0.0,
) -> int:
    """Gera vídeos para itens com roteiro pronto ainda sem vídeo. Retorna quantos gerados.

    `limit` conta vídeos GERADOS: itens pulados por falta de mídia não
    consomem a cota, senão os mesmos itens "aguardando mídia" no topo do
    ranking travariam a fila a cada rodada.

    `daily_limit` é o teto de vídeos nas últimas 24h (o monitor roda a cada
    2 min; sem isso ele esgota os créditos de TTS do mês em um dia).
    `tts_reserve_chars` deixa uma folga de caracteres no plano ElevenLabs.
    """
    with get_connection(db_path) as conn:
        if daily_limit is not None:
            already_today = count_videos_generated_since(conn, since=start_of_day())
            if already_today >= daily_limit:
                logger.info(
                    "Teto diário atingido (%d/%d vídeos hoje) — nada a gerar agora",
                    already_today,
                    daily_limit,
                )
                return 0
            remaining_today = daily_limit - already_today
            limit = remaining_today if limit is None else min(limit, remaining_today)

        pending = get_items_pending_video(conn, max_age_hours=max_age_hours)
        logger.info("%d item(ns) pendente(s) de geração de vídeo", len(pending))

        generated = 0
        skipped = 0
        for row in pending:
            if limit is not None and generated >= limit:
                break
            # a fila vem ordenada por pontuação efetiva: o primeiro abaixo do
            # piso significa que não há mais nada que valha uma vaga hoje
            score = row["effective_score"] or 0
            if min_score and score < min_score:
                logger.info(
                    "Melhor pauta restante vale %.1f (piso %.1f) — guardando a vaga do dia "
                    "pra algo mais forte",
                    score,
                    min_score,
                )
                break
            narration_length = len(
                build_narration_text(row["script_hook"], row["script_body"], row["script_cta"])
            )
            if tts_reserve_chars and not has_budget_for(narration_length, tts_reserve_chars):
                break
            try:
                result = generate_video_for_item(row, render=render, require_media=require_media)
            except MediaMissingError as exc:
                skipped += 1
                set_video_skip_reason(conn, row["id"], str(exc))
                conn.commit()
                logger.warning(
                    "Item %s pulado (aguardando mídia): %s — envie o fundo/música pelo painel",
                    row["id"],
                    exc,
                )
                continue
            except Exception:
                logger.exception(
                    "Falha ao gerar vídeo para item %s ('%s')", row["id"], row["title"]
                )
                continue

            save_video(
                conn,
                item_id=row["id"],
                audio_path=result["audio_path"],
                video_spec_path=result["spec_path"],
                video_path=result.get("video_path"),
                cover_path=result.get("cover_path"),
            )
            conn.commit()
            generated += 1
            logger.info("Vídeo gerado [item %s]: %s", row["id"], result.get("video_path", result["spec_path"]))

        logger.info(
            "video_gen finalizado: %d vídeo(s) gerado(s), %d aguardando mídia", generated, skipped
        )
        return generated


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Gera vídeos (TTS + legendas + render)")
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument("--limit", type=int, default=None, help="Limite de itens nesta rodada")
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Gera apenas áudio + spec JSON, sem renderizar com Remotion",
    )
    parser.add_argument(
        "--require-media",
        action="store_true",
        help="Pula itens sem vídeo de fundo ou música (não gera vídeo com gradiente)",
    )
    parser.add_argument(
        "--max-age-hours", type=float, default=None, help="Ignora notícias coletadas há mais de N horas"
    )
    parser.add_argument(
        "--daily-limit", type=int, default=None, help="Teto de vídeos gerados nas últimas 24h"
    )
    args = parser.parse_args()

    run(
        db_path=args.db,
        limit=args.limit,
        render=not args.no_render,
        require_media=args.require_media,
        max_age_hours=args.max_age_hours,
        daily_limit=args.daily_limit,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
