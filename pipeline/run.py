"""Orquestrador end-to-end: roda o pipeline completo em sequência.

collector -> dedupe -> script_gen -> video_gen -> publisher (dry-run por padrão)

Uso:
    uv run python -m pipeline.run [--limit N] [--publish-live] [--publish-mode inbox|direct]

Pensado para rodar via cron como um único job (em vez de 5 jobs separados).
Cada etapa é idempotente e continua mesmo se uma etapa anterior não gerar
itens novos (ex: nenhuma notícia relevante nesta rodada).
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

import collector.run as collector_run
import dedupe.run as dedupe_run
import publisher.run as publisher_run
import script_gen.run as script_gen_run
import video_gen.run as video_gen_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline")


def run_pipeline(
    db_path: str | None = None,
    feeds_path: str = collector_run.DEFAULT_FEEDS_PATH,
    limit: int | None = None,
    publish_dry_run: bool = True,
    publish_mode: str = "inbox",
    render_video: bool = True,
) -> dict:
    """Roda o pipeline completo uma vez. Retorna um resumo com contagens por etapa."""
    summary = {}

    logger.info("=== Etapa 1/5: collector ===")
    summary["collected"] = collector_run.run(feeds_path=feeds_path, db_path=db_path)

    logger.info("=== Etapa 2/5: dedupe ===")
    evaluated, relevant = dedupe_run.run(db_path=db_path)
    summary["evaluated"] = evaluated
    summary["relevant"] = relevant

    logger.info("=== Etapa 3/5: script_gen ===")
    summary["scripted"] = script_gen_run.run(db_path=db_path, limit=limit)

    logger.info("=== Etapa 4/5: video_gen ===")
    summary["videos"] = video_gen_run.run(db_path=db_path, limit=limit, render=render_video)

    logger.info("=== Etapa 5/5: publisher (dry_run=%s) ===", publish_dry_run)
    summary["published"] = publisher_run.run(
        db_path=db_path, limit=limit, mode=publish_mode, dry_run=publish_dry_run
    )

    logger.info("=== Pipeline finalizado: %s ===", summary)
    return summary


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Roda o pipeline completo end-to-end")
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument(
        "--feeds", default=collector_run.DEFAULT_FEEDS_PATH, help="Caminho do feeds.yaml"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limite de itens por etapa (script_gen/video_gen/publisher) nesta rodada",
    )
    parser.add_argument(
        "--publish-live",
        dest="publish_dry_run",
        action="store_false",
        default=True,
        help="Publica DE VERDADE no TikTok (padrão é dry-run)",
    )
    parser.add_argument(
        "--publish-mode", choices=["inbox", "direct"], default="inbox", help="Modo de publicação"
    )
    parser.add_argument(
        "--no-render",
        dest="render_video",
        action="store_false",
        default=True,
        help="Gera só áudio+spec, sem renderizar vídeo (útil sem Node/Remotion)",
    )
    args = parser.parse_args()

    run_pipeline(
        db_path=args.db,
        feeds_path=args.feeds,
        limit=args.limit,
        publish_dry_run=args.publish_dry_run,
        publish_mode=args.publish_mode,
        render_video=args.render_video,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
