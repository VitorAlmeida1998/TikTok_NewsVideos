"""Testes do assembler (build_video_spec, write_spec) e do orquestrador
video_gen/run.py, com mocks para TTS/transcrição/render (sem custo/rede)."""
import json
from unittest.mock import patch

from video_gen.assembler import build_narration_text, build_video_spec, write_spec


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


def test_write_spec_creates_json_file(tmp_path, monkeypatch):
    import video_gen.assembler as assembler_module

    monkeypatch.setattr(assembler_module, "SPECS_DIR", tmp_path / "specs")

    spec = {"itemId": 42, "hook": "h"}
    path = write_spec(spec, item_id=42)

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == spec
    assert path.name == "item_42.json"
