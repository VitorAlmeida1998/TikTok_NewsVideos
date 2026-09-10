"""Testes do gerador de roteiro (mock do runner do claude CLI, sem custo/chamadas reais)."""
import pytest

from script_gen.generator import ScriptGenError, _parse_script_response, generate_script


def _make_runner(response_text: str):
    def runner(prompt: str) -> str:
        return response_text

    return runner


def _format_response(
    hook="h", body="b", cta="c", description="d", game_name="", pronunciations=""
) -> str:
    return (
        f"HOOK: {hook}\n"
        f"BODY: {body}\n"
        f"CTA: {cta}\n"
        f"DESCRIPTION: {description}\n"
        f"GAME_NAME: {game_name}\n"
        f"PRONUNCIATIONS: {pronunciations}"
    )


def test_generate_script_returns_parsed_dict():
    expected = {
        "hook": "Vaza data de lançamento antes da hora!",
        "body": "Segundo informações do site, o jogo foi confirmado para o próximo ano.",
        "cta": "Comenta aqui se você tava esperando isso!",
        "description": "Some Game finalmente tem data! #fyp #gaming #somegame",
        "game_name": "Some Game",
        "pronunciations": "Some Game=Sâm Gueim",
    }
    runner = _make_runner(_format_response(**expected))

    result = generate_script(
        title="Big Game Gets Release Date",
        summary="The publisher confirmed next year.",
        source="ign",
        runner=runner,
    )

    assert result == expected


def test_generate_script_tolerates_quotes_and_apostrophes_in_fields():
    """Regressão: notícias com aspas no título (ex: falas citadas) não podem
    quebrar o parser — motivo pelo qual o formato não é mais JSON."""
    expected = {
        "hook": 'Ele disse "isso muda tudo" e o jogo ainda nem saiu!',
        "body": "Marvel's Wolverine teve o final vazado, segundo o autor do post \"eu vazei\".",
        "cta": 'Você diria "não acredito" ou já esperava?',
        "description": "Marvel's Wolverine vaza de novo! #fyp #gaming",
        "game_name": "Marvel's Wolverine",
        "pronunciations": "Marvel's Wolverine=Márvels Uólverin",
    }
    runner = _make_runner(_format_response(**expected))

    result = generate_script(title="T", summary="S", source="src", runner=runner)
    assert result == expected


def test_generate_script_strips_markdown_fences():
    expected = {
        "hook": "h", "body": "b", "cta": "c", "description": "d", "game_name": "", "pronunciations": ""
    }
    fenced = "```\n" + _format_response(**expected) + "\n```"
    runner = _make_runner(fenced)

    result = generate_script(title="T", summary="S", source="src", runner=runner)
    assert result == expected


def test_generate_script_defaults_optional_fields_when_absent():
    runner = _make_runner("HOOK: h\nBODY: b\nCTA: c")

    result = generate_script(title="T", summary="S", source="src", runner=runner)
    assert result == {
        "hook": "h", "body": "b", "cta": "c", "description": "", "game_name": "", "pronunciations": ""
    }


def test_generate_script_passes_prompt_with_title_and_summary():
    captured = {}

    def runner(prompt: str) -> str:
        captured["prompt"] = prompt
        return _format_response()

    generate_script(title="Meu Título", summary="Meu Resumo", source="ign", runner=runner)

    assert "Meu Título" in captured["prompt"]
    assert "Meu Resumo" in captured["prompt"]
    assert "ign" in captured["prompt"]


def test_parse_script_response_raises_on_missing_field():
    with pytest.raises(ValueError):
        _parse_script_response("HOOK: h\nBODY: b")


def test_parse_script_response_raises_on_empty_field():
    with pytest.raises(ValueError):
        _parse_script_response("HOOK: \nBODY: b\nCTA: c")


def test_parse_script_response_raises_on_unrecognized_format():
    with pytest.raises(ValueError):
        _parse_script_response("isso aqui não tem nenhum campo reconhecível")


def test_script_gen_error_is_raised_on_cli_failure():
    def failing_runner(prompt: str) -> str:
        raise ScriptGenError("claude CLI falhou (exit 1): some error")

    with pytest.raises(ScriptGenError):
        generate_script(title="T", summary="S", source="src", runner=failing_runner)
