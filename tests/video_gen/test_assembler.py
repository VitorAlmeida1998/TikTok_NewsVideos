"""Testes do assembler (build_video_spec, write_spec) e do orquestrador
video_gen/run.py, com mocks para TTS/transcrição/render (sem custo/rede)."""
import json
from unittest.mock import patch

from video_gen.assembler import build_narration_text, build_video_spec, derive_badge, write_spec


def test_build_narration_text_joins_parts():
    text = build_narration_text("Hook!", "Corpo da notícia.", "Comenta aí!")
    assert text == "Hook! Corpo da notícia. Comenta aí!"


def test_build_video_spec_structure(tmp_path):
    words = [{"word": "oi", "start": 0.0, "end": 0.3}]

    spec = build_video_spec(
        item_id=1,
        hook="h",
        body="b",
        cta="c",
        audio_relative_path="audio/item_1.mp3",
        words=words,
        source="ign",
        title="Título",
    )

    assert spec["itemId"] == 1
    assert spec["hook"] == "h"
    assert spec["words"] == words
    assert spec["audioPath"] == "audio/item_1.mp3"


def test_derive_badge_returns_empty_for_no_keywords():
    assert derive_badge(None) == ""
    assert derive_badge("") == ""


def test_derive_badge_maps_single_keyword():
    assert derive_badge("leak") == "VAZOU"
    assert derive_badge("confirmed") == "CONFIRMADO"
    assert derive_badge("trailer") == "TRAILER"


def test_derive_badge_respects_priority_when_multiple_match():
    # "leak" (VAZOU) tem prioridade sobre "confirmed" (CONFIRMADO) na ordem de regras.
    assert derive_badge("confirmed,leak") == "VAZOU"


def test_write_spec_creates_json_file(tmp_path, monkeypatch):
    import video_gen.assembler as assembler_module

    monkeypatch.setattr(assembler_module, "SPECS_DIR", tmp_path / "specs")

    spec = {"itemId": 42, "hook": "h"}
    path = write_spec(spec, item_id=42)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == spec
    assert path.name == "item_42.json"


def test_build_video_spec_carries_channel_branding_from_settings(monkeypatch):
    import video_gen.assembler as assembler_module

    monkeypatch.setattr(
        assembler_module,
        "load_settings",
        lambda: {"channel_handle": "Canal Novo", "channel_initials": "CN"},
    )
    spec = build_video_spec(
        item_id=1, hook="h", body="b", cta="c", audio_relative_path="a.mp3",
        words=[], source="ign", title="t",
    )
    assert spec["channelHandle"] == "Canal Novo"
    assert spec["channelInitials"] == "CN"
