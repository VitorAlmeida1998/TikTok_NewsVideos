"""Renderiza a CAPA (thumbnail) do vídeo: um PNG 1080x1920 com o hook grande
e estático, gerado pela composição Remotion `NewsCover` a partir do MESMO
spec JSON usado no vídeo.

Por que existe: o TikTok usa a capa na grade do perfil e nos resultados de
busca. Sem capa própria, ele usa o primeiro frame do vídeo — onde o hook
ainda está animando (letras entrando) e o fundo é o começo do clipe. Ou
seja: capa "quebrada" e sem nenhum texto que ajude alguém a clicar/achar.

O frame do clipe de fundo é escolhido aqui (não no componente): pegamos
~25% da duração real do clipe via ffprobe e passamos em `--frame`, então a
capa nunca cai no logo/tela preta do começo do trailer.

Vídeos gerados antes da capa existir podem receber a sua depois, sem gastar
TTS de novo (o spec já está salvo):

    uv run python -m video_gen.cover --backfill
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("video_gen.cover")

PROJECT_ROOT = Path(__file__).parent.parent
REMOTION_DIR = PROJECT_ROOT / "video_gen" / "remotion"
REMOTION_PUBLIC_DIR = REMOTION_DIR / "public"
COVERS_DIR = PROJECT_ROOT / "data" / "covers"

FPS = 30  # precisa bater com o FPS da composição NewsCover (Root.tsx)
# Fração da duração do clipe de fundo usada como frame da capa.
BACKGROUND_FRACTION = 0.25
# Teto de segurança: mesmo em clipe longo, não passa disso (a composição
# NewsCover tem 60s; e quanto mais tarde o frame, mais lento o seek).
MAX_BACKGROUND_SECONDS = 20.0


def _probe_duration_seconds(path: Path, timeout: int = 30) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return float(result.stdout.strip())
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def background_frame(spec: dict, public_dir: Path = REMOTION_PUBLIC_DIR) -> int:
    """Frame da composição a renderizar: ~25% do clipe de fundo (nunca o
    início). 0 quando não há clipe (fundo gradiente) ou o ffprobe falha."""
    relative = spec.get("backgroundVideoPath") or ""
    if not relative:
        return 0

    duration = _probe_duration_seconds(public_dir / relative)
    if not duration or duration <= 0:
        return 0

    seconds = min(duration * BACKGROUND_FRACTION, MAX_BACKGROUND_SECONDS)
    # margem pro fim do clipe: pedir o último frame às vezes devolve preto
    seconds = min(seconds, max(0.0, duration - 0.5))
    return int(seconds * FPS)


def render_cover(spec_path: str | Path, item_id: int, timeout: int = 300) -> Path:
    """Renderiza `data/covers/item_<id>.png` a partir do spec do vídeo.

    Levanta RuntimeError se o Remotion falhar (o chamador decide se isso é
    fatal — no pipeline, capa que falha não derruba o vídeo).
    """
    spec_path = Path(spec_path)
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = COVERS_DIR / f"item_{item_id}.png"

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    frame = background_frame(spec)

    cmd = [
        "npx",
        "remotion",
        "still",
        "NewsCover",
        str(output_path),
        f"--props={spec_path}",
        f"--frame={frame}",
    ]
    logger.info("Renderizando capa (item %s, frame %s): %s", item_id, frame, " ".join(cmd))

    result = subprocess.run(
        cmd, cwd=str(REMOTION_DIR), capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        logger.error("Falha ao renderizar capa do item %s:\n%s", item_id, result.stderr[-2000:])
        raise RuntimeError(f"remotion still falhou (item {item_id}): {result.stderr[-500:]}")

    logger.info("Capa renderizada: %s", output_path)
    return output_path


def backfill(db_path: str | None = None, limit: int | None = None) -> int:
    """Gera a capa dos vídeos que já existem e ainda não têm uma. Retorna
    quantas foram criadas."""
    from shared.db import get_connection, get_items_with_video

    created = 0
    with get_connection(db_path) as conn:
        pending = [
            row
            for row in get_items_with_video(conn)
            if not row["cover_path"] and row["video_spec_path"]
        ]
        if limit is not None:
            pending = pending[:limit]
        logger.info("%d vídeo(s) sem capa", len(pending))

        for row in pending:
            if not Path(row["video_spec_path"]).exists():
                logger.warning("Item %s: spec %s não existe, pulando", row["id"], row["video_spec_path"])
                continue
            try:
                cover_path = render_cover(row["video_spec_path"], row["id"])
            except Exception:
                logger.exception("Falha ao gerar capa do item %s", row["id"])
                continue
            conn.execute(
                "UPDATE news_items SET cover_path = ? WHERE id = ?", (str(cover_path), row["id"])
            )
            conn.commit()
            created += 1

    logger.info("Backfill de capas: %d criada(s)", created)
    return created


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description="Capas (thumbnails) dos vídeos")
    parser.add_argument(
        "--backfill", action="store_true", help="Gera a capa dos vídeos que ainda não têm"
    )
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de capas nesta rodada")
    args = parser.parse_args()

    if not args.backfill:
        parser.error("use --backfill (a capa do vídeo novo já sai junto com o vídeo)")
    backfill(db_path=args.db, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main() or 0)
