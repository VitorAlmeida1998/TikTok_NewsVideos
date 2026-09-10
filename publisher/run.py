"""Ponto de entrada do módulo publisher: envia vídeos prontos para o TikTok.

Uso:
    uv run python -m publisher.run [--db data/news.db] [--limit N]
                                    [--mode inbox|direct] [--dry-run]

Modo padrão é --dry-run (não publica nada de verdade, só simula e loga o que
faria). Requer TIKTOK_ACCESS_TOKEN no ambiente (.env) para publicar de fato.

Modos:
- inbox (padrão, mais seguro): envia como rascunho para a caixa de entrada
  do TikTok do usuário, que revisa e publica manualmente no app.
- direct: publica diretamente no perfil (requer escopo video.publish
  aprovado pelo TikTok — usar com cautela).

REGRA DO PROJETO: valide manualmente pelo menos 5 vídeos ponta a ponta
antes de rodar este módulo sem --dry-run.
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from publisher.tiktok_client import PublisherError, post_video_direct, post_video_to_inbox
from shared.db import get_connection, get_items_pending_publish, save_publish_result

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("publisher")


def run(
    db_path: str | None = None,
    limit: int | None = None,
    mode: str = "inbox",
    dry_run: bool = True,
) -> int:
    """Publica (ou simula publicar, se dry_run) vídeos prontos ainda não publicados.

    Retorna quantos itens foram processados (publicados ou simulados).
    """
    with get_connection(db_path) as conn:
        pending = get_items_pending_publish(conn)
        if limit is not None:
            pending = pending[:limit]

        logger.info(
            "%d item(ns) pendente(s) de publicação (mode=%s, dry_run=%s)",
            len(pending),
            mode,
            dry_run,
        )

        processed = 0
        for row in pending:
            if dry_run:
                logger.info(
                    "[DRY-RUN] publicaria item %s ('%s') via modo '%s': %s",
                    row["id"],
                    row["title"],
                    mode,
                    row["video_path"],
                )
                save_publish_result(conn, row["id"], publish_id="dry-run", status="dry_run")
                processed += 1
                continue

            try:
                if mode == "inbox":
                    result = post_video_to_inbox(row["video_path"])
                elif mode == "direct":
                    description = row["script_description"] if "script_description" in row.keys() else ""
                    title = (description or f"{row['script_hook']} {row['script_cta']}")[:150]
                    result = post_video_direct(row["video_path"], title=title)
                else:
                    raise ValueError(f"Modo inválido: {mode}")
            except PublisherError:
                logger.exception("Falha ao publicar item %s ('%s')", row["id"], row["title"])
                continue

            publish_id = result.get("data", {}).get("publish_id", "unknown")
            save_publish_result(conn, row["id"], publish_id=publish_id, status="submitted")
            processed += 1
            logger.info("Publicado [item %s]: publish_id=%s", row["id"], publish_id)

        logger.info("publisher finalizado: %d item(ns) processado(s)", processed)
        return processed


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Publica vídeos prontos no TikTok")
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument("--limit", type=int, default=None, help="Limite de itens nesta rodada")
    parser.add_argument(
        "--mode", choices=["inbox", "direct"], default="inbox", help="Modo de publicação"
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Não publica de verdade, só simula (padrão)",
    )
    parser.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Publica DE VERDADE no TikTok (desativa o dry-run)",
    )
    args = parser.parse_args()

    run(db_path=args.db, limit=args.limit, mode=args.mode, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main() or 0)
