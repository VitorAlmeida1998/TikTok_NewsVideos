"""Gerenciador simples de jobs em background (threads) para a webapp.

O Flask serve as requisições rápido; ações demoradas (gerar roteiro, gerar
vídeo, coletar notícias) rodam numa thread separada, com progresso/log
consultável via polling (GET /api/jobs/<id>).

Não é uma fila persistente — jobs vivem em memória do processo Flask.
Suficiente para uso pessoal single-user, que é o caso desta ferramenta.
"""
from __future__ import annotations

import contextlib
import io
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("webapp.jobs")


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"  # running | done | error
    log: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "log": self.log,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class _LogCapturingHandler(logging.Handler):
    """Handler de logging que acumula texto num buffer para o job."""

    def __init__(self, buffer: io.StringIO):
        super().__init__()
        self.buffer = buffer
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.write(self.format(record) + "\n")
        except Exception:
            pass


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, target, *args, **kwargs) -> str:
        """Inicia uma função `target(*args, **kwargs)` numa thread, capturando
        os logs do root logger durante a execução. Retorna o job_id.
        """
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, kind=kind)
        with self._lock:
            self._jobs[job_id] = job

        def _runner():
            buffer = io.StringIO()
            handler = _LogCapturingHandler(buffer)
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            try:
                result = target(*args, **kwargs)
                job.result = result if isinstance(result, dict) else {"value": result}
                job.status = "done"
            except Exception as exc:
                logger.exception("Job %s (%s) falhou", job_id, kind)
                job.error = str(exc)
                job.status = "error"
            finally:
                root_logger.removeHandler(handler)
                job.log = buffer.getvalue()
                job.finished_at = time.time()

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return job_id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]


# Instância única compartilhada pelo processo Flask (single-user, sem multi-worker).
job_manager = JobManager()
