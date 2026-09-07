"""Testes do gerador de roteiro (mock do runner do claude CLI, sem custo/chamadas reais)."""
import json

import pytest

from script_gen.generator import ScriptGenError, _parse_script_json, generate_script


def _make_runner(response_text: str):
    def runner(prompt: str) -> str:
        return response_text

    return runner


def test_generate_script_returns_parsed_dict():
    payload = {
        "hook": "Vaza data de lançamento antes da hora!",
        "body": "Segundo informações do site, o jogo foi confirmado para o próximo ano.",
        "cta": "Comenta aqui se você tava esperando isso!",
        "game_name": "Some Game",
    }
    runner = _make_runner(json.dumps(payload))

    result = generate_script(
        title="Big Game Gets Release Date",
        summary="The publisher confirmed next year.",
        source="ign",
        runner=runner,
    )

    assert result == payload


def test_generate_script_strips_markdown_fences():
    payload = {"hook": "h", "body": "b", "cta": "c", "game_name": ""}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    runner = _make_runner(fenced)

    result = generate_script(title="T", summary="S", source="src", runner=runner)
    assert result == payload


def test_generate_script_extracts_json_with_surrounding_text():
    payload = {"hook": "h", "body": "b", "cta": "c", "game_name": ""}
    noisy = f"Aqui está o roteiro:\n{json.dumps(payload)}\nEspero que ajude!"
    runner = _make_runner(noisy)

    result = generate_script(title="T", summary="S", source="src", runner=runner)
    assert result == payload


def test_generate_script_passes_prompt_with_title_and_summary():
    captured = {}

    def runner(prompt: str) -> str:
        captured["prompt"] = prompt
        return json.dumps({"hook": "h", "body": "b", "cta": "c"})

    generate_script(title="Meu Título", summary="Meu Resumo", source="ign", runner=runner)

    assert "Meu Título" in captured["prompt"]
    assert "Meu Resumo" in captured["prompt"]
    assert "ign" in captured["prompt"]


def test_parse_script_json_raises_on_missing_field():
    with pytest.raises(ValueError):
        _parse_script_json(json.dumps({"hook": "h", "body": "b"}))


def test_parse_script_json_raises_on_empty_field():
    with pytest.raises(ValueError):
        _parse_script_json(json.dumps({"hook": "", "body": "b", "cta": "c"}))


def test_parse_script_json_raises_on_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        _parse_script_json("not json at all, no braces")


def test_script_gen_error_is_raised_on_cli_failure():
    def failing_runner(prompt: str) -> str:
        raise ScriptGenError("claude CLI falhou (exit 1): some error")

    with pytest.raises(ScriptGenError):
        generate_script(title="T", summary="S", source="src", runner=failing_runner)
