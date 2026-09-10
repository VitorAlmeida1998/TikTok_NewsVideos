"""Monitor contínuo ("tempo real"): fica checando os feeds a cada poucos
minutos e, assim que entra notícia nova, ela passa na hora por
dedupe (ranking) -> script_gen -> video_gen, sem esperar rodada de cron nem
clique no painel.

Uso:
    uv run python -m pipeline.watch [--interval 120] [--limit 3] [--max-age-hours 48]
                                    [--no-require-media] [--once]

RSS não tem push: "tempo real" aqui é polling curto (default 2 min, 5 feeds —
leve pros sites). Cada ciclo grava data/watcher_status.json, que o painel lê
pra mostrar se o monitor está vivo e quando foi a última checagem.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

import collector.run as collector_run
import dedupe.run as dedupe_run
import script_gen.run as script_gen_run
import video_gen.run as video_gen_run
from publisher.schedule import BR_TZ, build_schedule
from shared.db import get_connection, get_publish_queue, schedule_publish
from shared.settings import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("watcher")

PROJECT_ROOT = Path(__file__).parent.parent
STATUS_PATH = PROJECT_ROOT / "data" / "watcher_status.json"
DEFAULT_INTERVAL_SECONDS = 120


def run_cycle(
    db_path: str | None = None,
    feeds_path: str = collector_run.DEFAULT_FEEDS_PATH,
    limit: int | None = 3,
    require_media: bool = True,
    max_age_hours: float | None = 48,
) -> dict:
    """Um ciclo completo: coleta -> ranking -> roteiro -> vídeo. Retorna contagens."""
    summary = {}
    summary["collected"] = collector_run.run(feeds_path=feeds_path, db_path=db_path)
    evaluated, relevant = dedupe_run.run(db_path=db_path)
    summary["evaluated"] = evaluated
    summary["relevant"] = relevant
    summary["scripted"] = script_gen_run.run(
        db_path=db_path, limit=limit, max_age_hours=max_age_hours
    )
    settings = load_settings()
    summary["videos"] = video_gen_run.run(
        db_path=db_path,
        limit=limit,
        require_media=require_media,
        max_age_hours=max_age_hours,
        # o monitor roda a cada 2 min: sem teto diário e sem guarda de cota,
        # um dia de execução esgota os créditos de TTS do mês inteiro
        daily_limit=int(settings.get("max_videos_per_day", 3)),
        tts_reserve_chars=int(settings.get("tts_reserve_chars", 0)),
        min_score=float(settings.get("min_score_to_generate", 0)),
    )
    summary["scheduled"] = refresh_publish_schedule(db_path=db_path)
    return summary


def refresh_publish_schedule(db_path: str | None = None) -> int:
    """Dá horário de publicação aos vídeos prontos que ainda não têm um, para
    a fila do painel já estar pronta quando o usuário chegar. Não mexe em
    horário já definido à mão. Retorna quantos foram agendados agora."""
    settings = load_settings()
    now = datetime.now(BR_TZ)
    scheduled_now = 0

    with get_connection(db_path) as conn:
        queue = [dict(row) for row in get_publish_queue(conn)]
        if not queue:
            return 0
        for post in build_schedule(queue, now, settings):
            if post.reason == "horário já definido":
                continue
            schedule_publish(conn, post.item_id, post.when)
            scheduled_now += 1
            if post.post_now:
                when_label = "AGORA"
            elif post.when:
                when_label = post.when.strftime("%d/%m %H:%M")
            else:
                when_label = "sem horário"
            logger.info("Item %s: publicar %s (%s)", post.item_id, when_label, post.reason)
    return scheduled_now


def write_status(path: Path, summary: dict, interval_seconds: int, cycle_seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    status = {
        "last_check": now.isoformat(),
        "interval_seconds": interval_seconds,
        "cycle_seconds": round(cycle_seconds, 1),
        **summary,
    }
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(path: Path = STATUS_PATH) -> dict | None:
    """Status do monitor pro painel: None se nunca rodou. Inclui `alive`
    (última checagem há menos de 3 intervalos) e `seconds_since_check`."""
    if not path.exists():
        return None
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(status["last_check"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    interval = status.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
    status["seconds_since_check"] = int(elapsed)
    status["alive"] = elapsed < 3 * interval + status.get("cycle_seconds", 0)
    return status


def watch_forever(
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    once: bool = False,
    status_path: Path = STATUS_PATH,
    **cycle_kwargs,
) -> None:
    logger.info("Monitor iniciado: checando feeds a cada %ds", interval_seconds)
    while True:
        started = time.monotonic()
        # um ciclo com render pode levar minutos: já marca "vivo" no início,
        # senão o painel diz "monitor ainda não rodou" enquanto ele trabalha
        write_status(status_path, {"running": True}, interval_seconds, 0.0)
        try:
            summary = run_cycle(**cycle_kwargs)
        except Exception:
            logger.exception("Ciclo do monitor falhou; tentando de novo no próximo intervalo")
            summary = {"error": True}
        cycle_seconds = time.monotonic() - started
        write_status(status_path, summary, interval_seconds, cycle_seconds)
        if summary.get("collected") or summary.get("videos"):
            logger.info("Ciclo (%.0fs): %s", cycle_seconds, summary)
        if once:
            return
        time.sleep(max(5.0, interval_seconds - cycle_seconds))


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Monitor contínuo de notícias -> vídeo")
    parser.add_argument("--db", default=None, help="Caminho do banco SQLite")
    parser.add_argument("--feeds", default=collector_run.DEFAULT_FEEDS_PATH)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Segundos entre checagens")
    parser.add_argument("--limit", type=int, default=3, help="Máximo de roteiros/vídeos por ciclo")
    parser.add_argument("--max-age-hours", type=float, default=48)
    parser.add_argument(
        "--no-require-media",
        dest="require_media",
        action="store_false",
        default=True,
        help="Gera vídeo mesmo sem fundo/música (fundo gradiente)",
    )
    parser.add_argument("--once", action="store_true", help="Roda um ciclo só e sai")
    args = parser.parse_args()

    watch_forever(
        interval_seconds=args.interval,
        once=args.once,
        db_path=args.db,
        feeds_path=args.feeds,
        limit=args.limit,
        require_media=args.require_media,
        max_age_hours=args.max_age_hours,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
