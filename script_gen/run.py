"""Ponto de entrada do módulo script_gen: gera roteiros para itens relevantes.

Uso:
    uv run python -m script_gen.run [--db data/news.db] [--limit N]

Requer ANTHROPIC_API_KEY no ambiente (.env).
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from script_gen.generator import DEFAULT_MODEL, generate_script
from shared.db import get_connection, get_items_pending_script, get_recent_hooks, save_script

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("script_gen")


def run(
    db_path: str | None = None,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    max_age_hours: float | None = None,
) -> int:
    """Gera roteiros para itens relevantes ainda sem script (mais relevantes
    primeiro; `max_age_hours` ignora notícia antiga). Retorna quantos foram gerados."""
    with get_connection(db_path) as conn:
        pending = get_items_pending_script(conn, max_age_hours=max_age_hours)
        if limit is not None:
            pending = pending[:limit]

        logger.info("%d item(ns) pendente(s) de geração de roteiro", len(pending))

        generated = 0
        for row in pending:
            try:
                script = generate_script(
                    title=row["title"],
                    summary=row["summary"] or "",
                    source=row["source"],
                    model=model,
                    recent_hooks=get_recent_hooks(conn),
                )
            except Exception:
                logger.exception(
                    "Falha ao gerar roteiro para item %s ('%s')", row["id"], row["title"]
                )
                continue

            save_script(
                conn,
                item_id=row["id"],
                hook=script["hook"],
                body=script["body"],
                cta=script["cta"],
                model=model,
                game_name=script.get("game_name", ""),
                description=script.get("description", ""),
                pronunciations=script.get("pronunciations", ""),
            )
            generated += 1
            logger.info("Roteiro gerado [item %s]: %s", row["id"], script["hook"])

        logger.info("script_gen finalizado: %d roteiro(s) gerado(s)", generated)
        return generated


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Gera roteiros PT-BR via Anthropic API")
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modelo Anthropic a usar")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limite de itens a processar nesta rodada"
    )
    parser.add_argument(
        "--max-age-hours", type=float, default=None, help="Ignora notícias coletadas há mais de N horas"
    )
    args = parser.parse_args()

    run(db_path=args.db, model=args.model, limit=args.limit, max_age_hours=args.max_age_hours)


if __name__ == "__main__":
    sys.exit(main() or 0)
