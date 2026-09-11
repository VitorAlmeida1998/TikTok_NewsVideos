"""Configurações editáveis pelo painel (voz, marca, agenda de publicação),
guardadas em data/settings.json.

Ficam fora do .env porque o painel precisa poder mudá-las em runtime sem
reiniciar o processo nem mexer em arquivo de credencial. Valores de voz
caem para ELEVENLABS_VOICE_ID do ambiente quando não definidos aqui.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"

# Horários de pico do público BR no TikTok (fuso America/Sao_Paulo), em
# "HH:MM". Almoço e a faixa da noite concentram o consumo de vídeo curto.
DEFAULT_PEAK_SLOTS = ["12:15", "18:45", "21:15"]

DEFAULTS: dict = {
    "voice_id": "",  # vazio = usa ELEVENLABS_VOICE_ID do .env
    "voice_label": "",  # nome só pra exibição no painel
    "channel_handle": "TikTok GameNews",
    "channel_initials": "GN",
    "peak_slots": DEFAULT_PEAK_SLOTS,
    "posts_per_day": 3,
    "min_gap_minutes": 150,
    # Notícia muito quente e muito fresca não espera o próximo pico: o valor
    # da notícia cai mais rápido que o ganho de postar no horário nobre.
    "hot_score": 18.0,
    "hot_max_age_hours": 3.0,
    # Acima disso a notícia não ganha horário de pico: já foi coberta por
    # todo mundo (ou já foi corrigida) e o vídeo precisa de revisão sua.
    "stale_hours": 48.0,
    # Teto de vídeos gerados por dia. O monitor roda a cada 2 min e a fila de
    # notícias é sempre maior que a cota de TTS: sem isso, um dia de execução
    # queima o mês inteiro de créditos do ElevenLabs. Casa com posts_per_day —
    # não adianta gerar mais vídeo do que se pretende postar.
    "max_videos_per_day": 3,
    # Folga de caracteres do ElevenLabs que nunca é consumida pelo automático
    # (deixa espaço pra você gerar/regerar algo à mão no fim do ciclo).
    "tts_reserve_chars": 2000,
    # Piso de pontuação pra gastar uma das poucas vagas do dia. Sem isso, a
    # notícia fraca que chega de manhã queima a vaga e a pauta forte que sai
    # à noite fica sem vídeo. Com 13 fontes sempre sobra coisa acima do piso.
    "min_score_to_generate": 12.0,
}


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    """Configurações atuais (defaults + o que estiver salvo no JSON)."""
    settings = dict(DEFAULTS)
    if path.exists():
        try:
            settings.update(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return settings


def save_settings(values: dict, path: Path = SETTINGS_PATH) -> dict:
    """Salva apenas as chaves conhecidas (o resto é ignorado) e devolve o
    estado final."""
    settings = load_settings(path)
    settings.update({k: v for k, v in values.items() if k in DEFAULTS})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def get_voice_id(path: Path = SETTINGS_PATH) -> str:
    """Voz escolhida no painel; se não houver, a do .env; se nem isso, a
    padrão do ElevenLabs."""
    return (
        load_settings(path).get("voice_id")
        or os.environ.get("ELEVENLABS_VOICE_ID")
        or "pNInz6obpgDQGcFmaJgB"  # Adam (padrão histórico do projeto)
    )
