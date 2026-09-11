"""Agenda de publicação manual: em que horário cada vídeo pronto deve ir pro ar.

Enquanto a Content Posting API não está aprovada, o upload é feito à mão —
então o que a ferramenta pode fazer é dizer O QUE postar e QUANDO, na ordem
certa. Duas regras:

1. Vídeos entram nos horários de pico do público BR (settings.peak_slots,
   fuso America/Sao_Paulo), respeitando um intervalo mínimo entre posts e um
   teto por dia.
2. Notícia muito quente e muito fresca é marcada como "postar agora": em
   notícia de games, a vantagem de chegar primeiro vale mais que o ganho de
   esperar o horário nobre — daqui a 6 horas o assunto já está em todo lugar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")


@dataclass
class ScheduledPost:
    item_id: int
    when: datetime | None  # None = postar agora, ou fora da fila (stale/duplicate)
    reason: str
    stale: bool = False  # notícia velha: não vale mais ocupar um horário
    duplicate: bool = False  # outro vídeo da mesma história já está na fila

    @property
    def post_now(self) -> bool:
        return self.when is None and not self.stale and not self.duplicate


def start_of_day(now: datetime | None = None) -> datetime:
    """Meia-noite de hoje no fuso BR — início da contagem do teto diário."""
    now = (now or datetime.now(BR_TZ)).astimezone(BR_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_slots(slots: list[str]) -> list[time]:
    """"12:15" -> time(12, 15), ordenados e ignorando entradas inválidas."""
    parsed = []
    for slot in slots:
        try:
            hour, minute = (int(part) for part in slot.split(":"))
            parsed.append(time(hour, minute))
        except (ValueError, TypeError):
            continue
    return sorted(parsed)


def upcoming_slots(
    now: datetime,
    slots: list[time],
    count: int,
    posts_per_day: int,
    min_gap_minutes: int,
    already_used: list[datetime] | None = None,
) -> list[datetime]:
    """Os próximos `count` horários livres, a partir de agora.

    `already_used` são horários já ocupados por vídeos agendados antes (contam
    para o teto diário e para o intervalo mínimo).
    """
    used = sorted(already_used or [])
    result: list[datetime] = []
    day = now.astimezone(BR_TZ).date()
    gap = timedelta(minutes=min_gap_minutes)

    for _ in range(60):  # no máximo 60 dias à frente; na prática sai na 1ª volta
        if len(result) >= count:
            break
        for slot in slots:
            if len(result) >= count:
                break
            when = datetime.combine(day, slot, tzinfo=BR_TZ)
            if when <= now:
                continue
            same_day = [u for u in used + result if u.astimezone(BR_TZ).date() == day]
            if len(same_day) >= posts_per_day:
                continue
            if any(abs(when - u) < gap for u in used + result):
                continue
            result.append(when)
        day += timedelta(days=1)

    return result


def build_schedule(
    items: list[dict],
    now: datetime,
    settings: dict,
) -> list[ScheduledPost]:
    """Distribui os vídeos prontos (já na ordem de prioridade) pelos horários.

    Cada item precisa de: id, effective_score, age_hours e (opcional)
    publish_scheduled_at já definido — respeitado como está.
    """
    slots = parse_slots(settings.get("peak_slots", []))
    posts_per_day = int(settings.get("posts_per_day", 3))
    min_gap = int(settings.get("min_gap_minutes", 150))
    hot_score = float(settings.get("hot_score", 18.0))
    hot_max_age = float(settings.get("hot_max_age_hours", 3.0))
    stale_hours = float(settings.get("stale_hours", 48.0))

    scheduled: list[ScheduledPost] = []
    used: list[datetime] = []
    pending: list[dict] = []
    stories_in_queue: dict[int, int] = {}  # story_group -> id do vídeo que ficou com a vaga

    for item in items:
        # dois vídeos do mesmo fato no perfil queimam credibilidade (e às vezes
        # se contradizem). O primeiro da fila fica; o outro sai de vez.
        story = item.get("story_group")
        if story is not None and story in stories_in_queue:
            scheduled.append(
                ScheduledPost(
                    item["id"],
                    None,
                    f"mesma história do #{stories_in_queue[story]}, que já está na fila",
                    duplicate=True,
                )
            )
            continue
        if story is not None:
            stories_in_queue[story] = item["id"]

        existing = item.get("publish_scheduled_at")
        if existing:
            when = datetime.fromisoformat(existing)
            used.append(when)
            scheduled.append(ScheduledPost(item["id"], when, "horário já definido"))
            continue

        score = float(item.get("effective_score") or 0)
        age = float(item.get("age_hours") or 0)
        if age > stale_hours:
            # notícia de dois dias não merece um horário de pico: ou já foi
            # coberta por todo mundo, ou pior, já foi corrigida/desatualizada
            scheduled.append(
                ScheduledPost(
                    item["id"],
                    None,
                    f"notícia de {age:.0f}h — provavelmente passou o ponto; revise antes de postar",
                    stale=True,
                )
            )
            continue
        if score >= hot_score and age <= hot_max_age:
            scheduled.append(
                ScheduledPost(
                    item["id"],
                    None,
                    f"notícia quente (score {score:.0f}) e fresca ({age:.1f}h) — não espere o pico",
                )
            )
            continue
        pending.append(item)

    times = upcoming_slots(now, slots, len(pending), posts_per_day, min_gap, used)
    for item, when in zip(pending, times):
        scheduled.append(ScheduledPost(item["id"], when, "próximo horário de pico livre"))
    for item in pending[len(times) :]:
        scheduled.append(ScheduledPost(item["id"], None, "sem horário livre na janela"))

    return scheduled
