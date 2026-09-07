"""Ponto de entrada do módulo video_gen: gera vídeo (TTS + legendas + render)
para itens que já têm roteiro pronto.

Uso:
    uv run python -m video_gen.run [--db data/news.db] [--limit N] [--no-render]

Requer ELEVENLABS_API_KEY no ambiente (.env). `--no-render` gera apenas o
áudio + spec JSON, sem chamar o Remotion (útil se Node/Remotion não estão
configurados no ambiente).
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from shared.db import get_connection, get_items_pending_video, save_video
from video_gen.assembler import generate_video_for_item

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("video_gen")


def run(
    db_path: str | None = None, limit: int | None = None, render: bool = True
) -> int:
    """Gera vídeos para itens com roteiro pronto ainda sem vídeo. Retorna quantos gerados."""
    with get_connection(db_path) as conn:
        pending = get_items_pending_video(conn)
        if limit is not None:
            pending = pending[:limit]

        logger.info("%d item(ns) pendente(s) de geração de vídeo", len(pending))

        generated = 0
        for row in pending:
            try:
                result = generate_video_for_item(row, render=render)
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
            )
            generated += 1
            logger.info("Vídeo gerado [item %s]: %s", row["id"], result.get("video_path", result["spec_path"]))

        logger.info("video_gen finalizado: %d vídeo(s) gerado(s)", generated)
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
    args = parser.parse_args()

    run(db_path=args.db, limit=args.limit, render=not args.no_render)


if __name__ == "__main__":
    sys.exit(main() or 0)
