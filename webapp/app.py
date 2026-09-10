"""Ponto de entrada da webapp Flask: dashboard local para gerenciar o pipeline
de notícias -> roteiro -> vídeo, com upload de fundo/música customizados.

Uso:
    uv run python -m webapp.app
    (acesse http://localhost:5000 no navegador)

Ferramenta de uso pessoal/local — sem autenticação, não expor na internet.
"""
from __future__ import annotations

import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

load_dotenv()

import collector.run as collector_run
import dedupe.run as dedupe_run
import script_gen.run as script_gen_run
import video_gen.run as video_gen_run
from pipeline.watch import read_status as read_watcher_status
from publisher.schedule import BR_TZ, build_schedule
from script_gen.generator import DEFAULT_MODEL, generate_script
from shared.db import (
    clear_video,
    count_items,
    get_connection,
    get_item,
    get_publish_queue,
    get_recent_hooks,
    get_status_counts,
    get_story_siblings,
    list_items,
    mark_posted,
    save_script,
    save_video,
    schedule_publish,
    update_script,
)
from shared.settings import load_settings, save_settings
from video_gen.assembler import generate_video_for_item
from video_gen.gameplay import CACHE_DIR as GAMEPLAY_CACHE_DIR
from video_gen.gameplay import MANUAL_CLIPS_DIR, slugify
from video_gen.music import CACHE_DIR as MUSIC_CACHE_DIR
from video_gen.tts import synthesize_speech
from webapp.icons import icon
from webapp.jobs import job_manager
from webapp.media import (
    MediaProcessingError,
    clear_gameplay_cache,
    clear_music_cache,
    probe_duration_seconds,
    process_uploaded_audio,
    process_uploaded_video,
)
from webapp.seo import check_seo, seo_score

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("webapp")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1GB, para upload de vídeo
app.jinja_env.globals["icon"] = icon

PAGE_SIZE = 20

PROJECT_ROOT = Path(__file__).parent.parent
VOICE_SAMPLES_DIR = PROJECT_ROOT / "data" / "voice_samples"

# Frase de amostra pra comparar vozes: mesma energia dos hooks reais (caixa
# alta, exclamação, reticências), porque é aí que a diferença entre uma voz
# nativa e uma voz inglesa falando português aparece.
VOICE_SAMPLE_TEXT = (
    "GENTE, o trailer de GTA 6 quebrou o mercado de console! "
    "As vendas dispararam... e ninguém esperava isso. Vem ver!"
)

# A chave desta conta não tem permissão `voices_read`, então não dá pra listar
# a biblioteca pela API. Estes são IDs públicos e estáveis da biblioteca do
# ElevenLabs, só como ponto de partida — todos com sotaque inglês. A voz
# nativa PT-BR vem do campo "colar ID" (biblioteca do site).
VOICE_CANDIDATES = [
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "note": "voz atual do projeto — masculina, inglesa"},
    {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "note": "masculina, mais jovem"},
    {"voice_id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "note": "masculina, grave"},
    {"voice_id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "note": "masculina, locutor"},
    {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "note": "feminina, calma"},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "note": "feminina, animada"},
]

_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9]{8,40}$")


def voice_sample_path(voice_id: str) -> Path:
    return VOICE_SAMPLES_DIR / f"{voice_id}.mp3"


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
        watcher=read_watcher_status(),
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


# --- Fila de publicação ----------------------------------------------------


def _format_slot(when: datetime | None) -> str:
    """"hoje 18:45" / "amanhã 12:15" / "12/09 21:15", no fuso do Brasil."""
    if when is None:
        return ""
    local = when.astimezone(BR_TZ)
    today = datetime.now(BR_TZ).date()
    delta_days = (local.date() - today).days
    if delta_days == 0:
        return f"hoje {local:%H:%M}"
    if delta_days == 1:
        return f"amanhã {local:%H:%M}"
    return f"{local:%d/%m} {local:%H:%M}"


@app.route("/publicar")
def publish_queue_page():
    settings = load_settings()
    with get_connection() as conn:
        queue = [dict(row) for row in get_publish_queue(conn)]
        posted = [dict(row) for row in get_publish_queue(conn, include_posted=True) if row["posted_at"]]

    plan = {post.item_id: post for post in build_schedule(queue, datetime.now(BR_TZ), settings)}
    for item in queue:
        post = plan.get(item["id"])
        item["slot_label"] = _format_slot(post.when) if post else ""
        item["post_now"] = post.post_now if post else False
        item["stale"] = post.stale if post else False
        item["duplicate"] = post.duplicate if post else False
        item["slot_reason"] = post.reason if post else ""
        item["has_cover"] = bool(item.get("cover_path")) and Path(item["cover_path"]).exists()

    return render_template(
        "publish.html",
        queue=queue,
        posted=posted[:10],
        settings=settings,
        peak_slots_text=", ".join(settings.get("peak_slots", [])),
    )


@app.route("/publicar/recalcular", methods=["POST"])
def recalc_schedule():
    """Refaz a agenda inteira do zero (inclusive horários já definidos) — é o
    botão pra usar depois de mudar os horários de pico ou de postar fora de ordem."""
    settings = load_settings()
    with get_connection() as conn:
        for row in get_publish_queue(conn):
            schedule_publish(conn, row["id"], None)
        queue = [dict(row) for row in get_publish_queue(conn)]
        for post in build_schedule(queue, datetime.now(BR_TZ), settings):
            schedule_publish(conn, post.item_id, post.when)
    return redirect(url_for("publish_queue_page"))


@app.route("/publicar/config", methods=["POST"])
def save_publish_settings():
    slots = [slot.strip() for slot in request.form.get("peak_slots", "").split(",") if slot.strip()]
    save_settings(
        {
            "peak_slots": slots,
            "posts_per_day": request.form.get("posts_per_day", 3, type=int),
            "min_gap_minutes": request.form.get("min_gap_minutes", 150, type=int),
            # o teto de geração acompanha o de publicação: gerar mais vídeo do
            # que se pretende postar só queima crédito de TTS
            "max_videos_per_day": request.form.get("posts_per_day", 3, type=int),
        }
    )
    return redirect(url_for("publish_queue_page"))


@app.route("/marca", methods=["POST"])
def save_brand_settings():
    """Nome/iniciais do canal — aparecem na marca d'água do vídeo, no card
    'segue o perfil' e na capa. Valem no próximo vídeo gerado."""
    save_settings(
        {
            "channel_handle": request.form.get("channel_handle", "").strip(),
            "channel_initials": request.form.get("channel_initials", "").strip()[:3].upper(),
        }
    )
    return redirect(request.form.get("next") or url_for("publish_queue_page"))


@app.route("/item/<int:item_id>/postado", methods=["POST"])
def toggle_posted(item_id: int):
    posted = request.form.get("posted", "1") == "1"
    with get_connection() as conn:
        mark_posted(conn, item_id, posted=posted)
    return redirect(request.form.get("next") or url_for("publish_queue_page"))


# --- Comparador de vozes ---------------------------------------------------


@app.route("/vozes")
def voices_page():
    settings = load_settings()
    current = settings.get("voice_id") or ""
    candidates = [dict(candidate) for candidate in VOICE_CANDIDATES]

    extra = settings.get("voice_id")
    if extra and not any(c["voice_id"] == extra for c in candidates):
        candidates.insert(
            0,
            {
                "voice_id": extra,
                "name": settings.get("voice_label") or "Voz personalizada",
                "note": "colada por você",
            },
        )

    for candidate in candidates:
        candidate["has_sample"] = voice_sample_path(candidate["voice_id"]).exists()
        candidate["is_current"] = candidate["voice_id"] == current

    return render_template(
        "voices.html",
        candidates=candidates,
        settings=settings,
        sample_text=VOICE_SAMPLE_TEXT,
        current_voice=current,
    )


@app.route("/vozes/amostra", methods=["POST"])
def generate_voice_sample():
    payload = request.get_json(silent=True) or {}
    voice_id = (request.form.get("voice_id") or payload.get("voice_id") or "").strip()
    if not _VOICE_ID_RE.match(voice_id):
        return jsonify({"error": "voice_id inválido — copie o ID da biblioteca do ElevenLabs"}), 400

    def _task():
        output = voice_sample_path(voice_id)
        result = synthesize_speech(VOICE_SAMPLE_TEXT, output, voice_id=voice_id)
        return {"voice_id": voice_id, "path": str(result.audio_path)}

    try:
        job_id = job_manager.start("voice_sample", _task, key=f"voice:{voice_id}")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"job_id": job_id})


@app.route("/vozes/usar", methods=["POST"])
def use_voice():
    voice_id = (request.form.get("voice_id") or "").strip()
    if not _VOICE_ID_RE.match(voice_id):
        return "voice_id inválido", 400
    save_settings({"voice_id": voice_id, "voice_label": request.form.get("voice_label", "").strip()})
    return redirect(url_for("voices_page"))


@app.route("/media/voice-sample/<voice_id>")
def media_voice_sample(voice_id: str):
    if not _VOICE_ID_RE.match(voice_id):
        return "Não encontrado", 404
    path = voice_sample_path(voice_id)
    if not path.exists():
        return "Não encontrado", 404
    return send_file(path, conditional=True)


# --- Detalhe do item -------------------------------------------------------


@app.route("/item/<int:item_id>")
def item_detail(item_id: int):
    with get_connection() as conn:
        item = get_item(conn, item_id)
        if item is None:
            return "Item não encontrado", 404
        # o próprio hook sai da lista, senão ele sempre acusa repetição consigo mesmo
        recent_hooks = [h for h in get_recent_hooks(conn, limit=11) if h != item["script_hook"]][:10]
        siblings = get_story_siblings(conn, item_id)

    seo_checks = check_seo(item, recent_hooks) if item["script_body"] else []
    seo_passed, seo_total = seo_score(seo_checks)

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
        seo_checks=seo_checks,
        seo_passed=seo_passed,
        seo_total=seo_total,
        siblings=siblings,
    )


@app.route("/item/<int:item_id>/script", methods=["POST"])
def save_item_script(item_id: int):
    hook = request.form.get("hook", "").strip()
    body = request.form.get("body", "").strip()
    cta = request.form.get("cta", "").strip()
    description = request.form.get("description", "").strip()
    pronunciations = request.form.get("pronunciations", "").strip()
    game_name = request.form.get("game_name", "").strip()

    with get_connection() as conn:
        update_script(
            conn,
            item_id,
            hook=hook,
            body=body,
            cta=cta,
            game_name=game_name,
            description=description,
            pronunciations=pronunciations,
        )

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
                description=script.get("description", ""),
                pronunciations=script.get("pronunciations", ""),
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
                cover_path=result.get("cover_path"),
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
    download = request.args.get("download") == "1"
    return send_file(
        item["video_path"],
        conditional=not download,
        as_attachment=download,
        download_name=f"item_{item_id}.mp4" if download else None,
    )


@app.route("/media/cover/<int:item_id>")
def media_cover(item_id: int):
    """Capa (thumbnail) gerada junto com o vídeo — é o que vai no upload."""
    with get_connection() as conn:
        item = get_item(conn, item_id)
    cover = item["cover_path"] if item else None
    if not cover or not Path(cover).exists():
        return "Capa não encontrada", 404
    download = request.args.get("download") == "1"
    return send_file(
        cover,
        conditional=not download,
        as_attachment=download,
        download_name=f"capa_{item_id}.png" if download else None,
    )


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
