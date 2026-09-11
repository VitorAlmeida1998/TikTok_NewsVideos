"""Gerenciador simples de jobs em background (threads) para a webapp.

O Flask serve as requisições rápido; ações demoradas (gerar roteiro, gerar
vídeo, coletar notícias) rodam numa thread separada, com progresso/log
consultável via polling (GET /api/jobs/<id>).

Não é uma fila persistente — jobs vivem em memória do processo Flask.
Suficiente para uso pessoal single-user, que é o caso desta ferramenta.
"""
from __future__ import annotations

import contextlib
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


MAX_LOG_CHARS = 20_000  # só o fim interessa; evita job longo comer memória


class _LogCapturingHandler(logging.Handler):
    """Handler de logging que escreve direto no `job.log`, linha a linha.

    Escrever no job a cada registro (em vez de despejar um buffer no fim) é o
    que faz o log aparecer AO VIVO no painel: o polling lê `job.log` enquanto
    a tarefa ainda roda.

    Filtra por thread: como o handler é anexado ao ROOT logger (global) para
    capturar logs de qualquer módulo, jobs rodando em paralelo em threads
    diferentes receberiam logs uns dos outros se não houvesse esse filtro
    (o root logger é compartilhado pelo processo inteiro).
    """

    def __init__(self, job: Job, thread_id: int):
        super().__init__()
        self.job = job
        self.thread_id = thread_id
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self.thread_id:
            return
        try:
            line = self.format(record) + "\n"
        except Exception:
            return
        log = self.job.log + line
        self.job.log = log[-MAX_LOG_CHARS:] if len(log) > MAX_LOG_CHARS else log


class JobManager:
    MAX_JOBS_KEPT = 200  # evita crescimento ilimitado de memória em uso prolongado

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._active_keys: set[str] = set()

    def _prune_locked(self) -> None:
        """Remove os jobs mais antigos além do limite. Deve ser chamado com
        self._lock já adquirido."""
        if len(self._jobs) <= self.MAX_JOBS_KEPT:
            return
        ordered = sorted(self._jobs.values(), key=lambda j: j.created_at)
        for job in ordered[: len(self._jobs) - self.MAX_JOBS_KEPT]:
            self._jobs.pop(job.id, None)

    def start(self, kind: str, target, *args, key: str | None = None, **kwargs) -> str:
        """Inicia uma função `target(*args, **kwargs)` numa thread, capturando
        os logs do root logger durante a execução. Retorna o job_id.

        `key` opcional identifica o "recurso" afetado (ex: f"video:{item_id}")
        — se já houver um job em execução com a mesma key, recusa iniciar um
        novo (evita duas gerações simultâneas escrevendo nos mesmos arquivos
        de saída, ex: dois cliques rápidos em "Gerar vídeo" no mesmo item).
        Levanta RuntimeError nesse caso.
        """
        with self._lock:
            if key is not None and key in self._active_keys:
                raise RuntimeError(
                    f"Já existe uma tarefa em execução para '{key}' — aguarde terminar."
                )
            job_id = uuid.uuid4().hex[:12]
            job = Job(id=job_id, kind=kind)
            self._jobs[job_id] = job
            if key is not None:
                self._active_keys.add(key)
            self._prune_locked()

        def _runner():
            handler = _LogCapturingHandler(job, thread_id=threading.get_ident())
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
                job.finished_at = time.time()
                if key is not None:
                    with self._lock:
                        self._active_keys.discard(key)

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
