"""Testes do gerenciador de jobs em background (webapp/jobs.py): proteção
contra concorrência (mesma key) e isolamento de logs entre threads."""
import threading
import time

from webapp.jobs import JobManager


def test_two_jobs_without_key_both_start():
    mgr = JobManager()
    ev = threading.Event()

    def task():
        ev.wait(timeout=2)
        return {"ok": True}

    id1 = mgr.start("test", task)
    id2 = mgr.start("test", task)
    assert id1 != id2
    ev.set()


def test_second_job_with_same_key_is_rejected_while_running():
    mgr = JobManager()
    release = threading.Event()
    started = threading.Event()

    def task():
        started.set()
        release.wait(timeout=5)
        return {"ok": True}

    mgr.start("test", task, key="shared-key")
    started.wait(timeout=2)  # garante que o primeiro job já está rodando

    try:
        mgr.start("test", task, key="shared-key")
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError as exc:
        assert "shared-key" in str(exc)
    finally:
        release.set()


def test_same_key_allowed_again_after_first_job_finishes():
    mgr = JobManager()

    def quick_task():
        return {"ok": True}

    job_id = mgr.start("test", quick_task, key="reusable-key")
    # espera terminar
    for _ in range(50):
        job = mgr.get(job_id)
        if job.status != "running":
            break
        time.sleep(0.05)

    # agora deve permitir de novo, sem lançar
    job_id2 = mgr.start("test", quick_task, key="reusable-key")
    assert job_id2 != job_id


def test_job_logs_are_isolated_per_thread():
    """Regressão: o handler de captura de log é anexado ao ROOT logger
    (global), então sem filtro por thread, jobs concorrentes vazam logs
    um do outro (bug encontrado e corrigido)."""
    import logging

    logging.getLogger().setLevel(logging.INFO)
    test_logger = logging.getLogger("test.jobs")
    test_logger.setLevel(logging.INFO)

    mgr = JobManager()
    barrier = threading.Barrier(2)

    def task_a():
        barrier.wait(timeout=2)
        test_logger.info("MENSAGEM_EXCLUSIVA_A")
        time.sleep(0.1)
        return {}

    def task_b():
        barrier.wait(timeout=2)
        test_logger.info("MENSAGEM_EXCLUSIVA_B")
        time.sleep(0.1)
        return {}

    id_a = mgr.start("test", task_a)
    id_b = mgr.start("test", task_b)

    for _ in range(50):
        ja, jb = mgr.get(id_a), mgr.get(id_b)
        if ja.status != "running" and jb.status != "running":
            break
        time.sleep(0.05)

    job_a = mgr.get(id_a)
    job_b = mgr.get(id_b)

    assert "MENSAGEM_EXCLUSIVA_A" in job_a.log
    assert "MENSAGEM_EXCLUSIVA_B" not in job_a.log
    assert "MENSAGEM_EXCLUSIVA_B" in job_b.log
    assert "MENSAGEM_EXCLUSIVA_A" not in job_b.log


def test_prune_keeps_only_max_jobs():
    mgr = JobManager()
    mgr.MAX_JOBS_KEPT = 5

    def quick_task():
        return {}

    ids = []
    for _ in range(10):
        job_id = mgr.start("test", quick_task)
        ids.append(job_id)
        # espera terminar antes de iniciar o próximo (evita race no teste)
        for _ in range(50):
            if mgr.get(job_id).status != "running":
                break
            time.sleep(0.02)

    assert len(mgr._jobs) <= 5
    # os mais recentes devem ter sobrevivido
    assert mgr.get(ids[-1]) is not None
