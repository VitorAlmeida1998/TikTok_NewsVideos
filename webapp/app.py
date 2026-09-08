"""Ponto de entrada da webapp Flask: dashboard local para gerenciar o pipeline
de notícias -> roteiro -> vídeo, com upload de fundo/música customizados.

Uso:
    uv run python -m webapp.app
    (acesse http://localhost:5000 no navegador)

Ferramenta de uso pessoal/local — sem autenticação, não expor na internet.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

load_dotenv()

import collector.run as collector_run
import dedupe.run as dedupe_run
import script_gen.run as script_gen_run
import video_gen.run as video_gen_run
from script_gen.generator import DEFAULT_MODEL, generate_script
from shared.db import (
    clear_video,
    count_items,
    get_connection,
    get_item,
    get_status_counts,
    list_items,
    save_script,
    save_video,
    update_script,
)
from video_gen.assembler import generate_video_for_item
from video_gen.gameplay import CACHE_DIR as GAMEPLAY_CACHE_DIR
from video_gen.gameplay import MANUAL_CLIPS_DIR, slugify
from video_gen.music import CACHE_DIR as MUSIC_CACHE_DIR
from webapp.jobs import job_manager
from webapp.media import (
    MediaProcessingError,
    clear_gameplay_cache,
    clear_music_cache,
    probe_duration_seconds,
    process_uploaded_audio,
    process_uploaded_video,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("webapp")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB, para upload de vídeo

PAGE_SIZE = 20


# --- Dashboard -----------------------------------------------------------


@app.route("/")
def index():
    status = request.args.get("status") or None
    search = request.args.get("q") or None
    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * PAGE_SIZE

    with get_connection() as conn:
        items = list_items(conn, status=status, search=search, limit=PAGE_SIZE, offset=offset)
        total = count_items(conn, status=status, search=search)
        counts = get_status_counts(conn)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    return render_template(
        "index.html",
        items=items,
        counts=counts,
        status=status,
        search=search or "",
        page=page,
        total_pages=total_pages,
        total=total,
    )


@app.route("/collect", methods=["POST"])
def collect():
    def _task():
        collected = collector_run.run()
        evaluated, relevant = dedupe_run.run()
        return {"collected": collected, "evaluated": evaluated, "relevant": relevant}

    try:
        job_id = job_manager.start("collect", _task, key="collect")
    except RuntimeError:
        # já tem uma coleta em andamento — só leva pra tela de tarefas mesmo assim
        pass
    else:
        return redirect(url_for("jobs_page", highlight=job_id))
    return redirect(url_for("jobs_page"))


@app.route("/bulk/generate-scripts", methods=["POST"])
def bulk_generate_scripts():
    limit = request.form.get("limit", 10, type=int)

    def _task():
        generated = script_gen_run.run(limit=limit)
        return {"generated": generated}

    try:
        job_id = job_manager.start("bulk_script", _task, key="bulk_script")
    except RuntimeError:
        return redirect(url_for("jobs_page"))
    return redirect(url_for("jobs_page", highlight=job_id))


@app.route("/bulk/generate-videos", methods=["POST"])
def bulk_generate_videos():
    limit = request.form.get("limit", 10, type=int)

    def _task():
        generated = video_gen_run.run(limit=limit)
        return {"generated": generated}

    try:
        job_id = job_manager.start("bulk_video", _task, key="bulk_video")
    except RuntimeError:
        return redirect(url_for("jobs_page"))
    return redirect(url_for("jobs_page", highlight=job_id))


# --- Detalhe do item -------------------------------------------------------


@app.route("/item/<int:item_id>")
def item_detail(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
    if item is None:
        return "Item não encontrado", 404

    game_name = item["game_name"] or ""
    slug = slugify(game_name) if game_name else None

    background_path = GAMEPLAY_CACHE_DIR / f"{slug}.mp4" if slug else None
    music_path = MUSIC_CACHE_DIR / f"{slug}.mp3" if slug else None
    manual_clip_paths = []
    if slug:
        for ext in [".mp4", ".mov", ".mkv", ".webm", ".avi"]:
            candidate = MANUAL_CLIPS_DIR / f"{slug}{ext}"
            if candidate.exists():
                manual_clip_paths.append(candidate)

    has_background = background_path is not None and background_path.exists()
    has_music = music_path is not None and music_path.exists()
    background_duration = probe_duration_seconds(background_path) if has_background else None
    music_duration = probe_duration_seconds(music_path) if has_music else None
    narration_duration = probe_duration_seconds(item["audio_path"]) if item["audio_path"] else None

    return render_template(
        "item.html",
        item=item,
        has_background=has_background,
        has_music=has_music,
        background_duration=background_duration,
        music_duration=music_duration,
        narration_duration=narration_duration,
        slug=slug,
    )


@app.route("/item/<int:item_id>/script", methods=["POST"])
def save_item_script(item_id: int):
    hook = request.form.get("hook", "").strip()
    body = request.form.get("body", "").strip()
    cta = request.form.get("cta", "").strip()
    game_name = request.form.get("game_name", "").strip()

    with get_connection() as conn:
        update_script(conn, item_id, hook=hook, body=body, cta=cta, game_name=game_name)

    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/generate-script", methods=["POST"])
def generate_item_script(item_id: int):
    def _task():
        with get_connection() as conn:
            item = get_item(conn, item_id)
            if item is None:
                raise ValueError(f"Item {item_id} não encontrado")

            script = generate_script(
                title=item["title"], summary=item["summary"] or "", source=item["source"]
            )
            save_script(
                conn,
                item_id=item_id,
                hook=script["hook"],
                body=script["body"],
                cta=script["cta"],
                model=DEFAULT_MODEL,
                game_name=script.get("game_name", ""),
            )
        return {"item_id": item_id, "hook": script["hook"]}

    try:
        job_id = job_manager.start("generate_script", _task, key=f"script:{item_id}")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"job_id": job_id})


@app.route("/item/<int:item_id>/generate-video", methods=["POST"])
def generate_item_video(item_id: int):
    def _task():
        with get_connection() as conn:
            item = get_item(conn, item_id)
            if item is None:
                raise ValueError(f"Item {item_id} não encontrado")
            if not item["script_body"]:
                raise ValueError("Item ainda não tem roteiro gerado")

            result = generate_video_for_item(item, render=True)
            save_video(
                conn,
                item_id=item_id,
                audio_path=result["audio_path"],
                video_spec_path=result["spec_path"],
                video_path=result.get("video_path"),
            )
        return result

    try:
        job_id = job_manager.start("generate_video", _task, key=f"video:{item_id}")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"job_id": job_id})


@app.route("/item/<int:item_id>/reset-video", methods=["POST"])
def reset_item_video(item_id: int):
    """Limpa o vídeo gerado do item, permitindo regenerar do zero (ex: após
    trocar o fundo/música customizados). Também apaga os arquivos físicos
    antigos (áudio/vídeo/spec) do disco, para não deixar órfãos acumulando
    em data/videos, data/audio e data/video_specs."""
    with get_connection() as conn:
        item = get_item(conn, item_id)
        if item:
            for path_str in (item["audio_path"], item["video_spec_path"], item["video_path"]):
                if path_str:
                    Path(path_str).unlink(missing_ok=True)
        clear_video(conn, item_id)
    return redirect(url_for("item_detail", item_id=item_id))


# --- Upload de mídia customizada (fundo/música) ---------------------------


@app.route("/item/<int:item_id>/upload-background", methods=["POST"])
def upload_background(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
    game_name = (request.form.get("game_name") or (item["game_name"] if item else "")).strip()
    if not game_name:
        return "Defina o nome do jogo antes de enviar o vídeo de fundo", 400

    file = request.files.get("video_file")
    if not file or file.filename == "":
        return "Nenhum arquivo enviado", 400

    start_seconds = request.form.get("start_seconds", 0.0, type=float)
    duration_seconds = request.form.get("duration_seconds", 60.0, type=float)

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        process_uploaded_video(
            tmp_path, game_name, start_seconds=start_seconds, duration_seconds=duration_seconds
        )
    except MediaProcessingError as exc:
        logger.warning("Falha ao processar vídeo enviado para '%s': %s", game_name, exc)
        return (
            f"Não foi possível processar o vídeo enviado — verifique se o arquivo não está "
            f"corrompido e se o início/duração do trecho estão dentro da duração real do "
            f"vídeo. Detalhe técnico: {exc}",
            400,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/upload-music", methods=["POST"])
def upload_music(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
    game_name = (request.form.get("game_name") or (item["game_name"] if item else "")).strip()
    if not game_name:
        return "Defina o nome do jogo antes de enviar a música de fundo", 400

    file = request.files.get("audio_file")
    if not file or file.filename == "":
        return "Nenhum arquivo enviado", 400

    start_seconds = request.form.get("start_seconds", 0.0, type=float)
    duration_seconds = request.form.get("duration_seconds", 60.0, type=float)

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        process_uploaded_audio(
            tmp_path, game_name, start_seconds=start_seconds, duration_seconds=duration_seconds
        )
    except MediaProcessingError as exc:
        logger.warning("Falha ao processar áudio enviado para '%s': %s", game_name, exc)
        return (
            f"Não foi possível processar o áudio enviado — verifique se o arquivo não está "
            f"corrompido e se o início/duração do trecho estão dentro da duração real do "
            f"áudio. Detalhe técnico: {exc}",
            400,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/clear-background", methods=["POST"])
def clear_background(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
    if item and item["game_name"]:
        clear_gameplay_cache(item["game_name"])
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/clear-music", methods=["POST"])
def clear_music(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
    if item and item["game_name"]:
        clear_music_cache(item["game_name"])
    return redirect(url_for("item_detail", item_id=item_id))


# --- Servir mídia (preview) ------------------------------------------------


@app.route("/media/video/<int:item_id>")
def media_video(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
    if not item or not item["video_path"] or not Path(item["video_path"]).exists():
        return "Vídeo não encontrado", 404
    return send_file(item["video_path"], conditional=True)


@app.route("/media/background/<slug>")
def media_background(slug: str):
    path = GAMEPLAY_CACHE_DIR / f"{slug}.mp4"
    if not path.exists():
        return "Não encontrado", 404
    return send_file(path, conditional=True)


@app.route("/media/music/<slug>")
def media_music(slug: str):
    path = MUSIC_CACHE_DIR / f"{slug}.mp3"
    if not path.exists():
        return "Não encontrado", 404
    return send_file(path, conditional=True)


# --- Jobs (progresso de tarefas em background) -----------------------------


@app.route("/jobs")
def jobs_page():
    highlight = request.args.get("highlight")
    jobs = job_manager.list_recent()
    return render_template("jobs.html", jobs=jobs, highlight=highlight)


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    job = job_manager.get(job_id)
    if job is None:
        return jsonify({"error": "job não encontrado"}), 404
    return jsonify(job.to_dict())


def main():
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
