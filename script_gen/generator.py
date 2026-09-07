"""Geração de roteiro em português via Claude Code CLI (`claude -p`), usando a
assinatura Claude Pro/Max do usuário em vez da API paga por token.

Por que CLI e não o SDK da Anthropic:
- O usuário tem assinatura Claude Pro/Max (claude.ai), que dá acesso ao
  `claude` CLI autenticado via OAuth — sem custo adicional por chamada.
- O SDK Python (anthropic.Anthropic) usa API keys com billing separado
  por token (console.anthropic.com/settings/billing), que é uma conta
  diferente e pode estar sem crédito.
- Rodamos `claude -p "<prompt>"` como subprocess, com ANTHROPIC_API_KEY
  removida do ambiente do subprocesso para forçar o uso do login OAuth
  (a env var, se presente, tem prioridade sobre o login e faria o CLI
  tentar cobrar da API paga).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess

logger = logging.getLogger("script_gen")

DEFAULT_MODEL = "claude-cli"  # marcador; o modelo real é decidido pela assinatura/CLI

SYSTEM_PROMPT = """\
Você é um criador de conteúdo brasileiro, do tipo que grava vídeo curto de \
games pro TikTok falando direto pra câmera, com MUITA empolgação e energia \
de verdade — tipo hypado, envolvido, nunca robótico ou de "apresentador de \
telejornal". Seu público é jovem, gamer, já cansado de vídeo sem graça.

Você recebe uma notícia de games em inglês (título + resumo) e deve gerar \
um roteiro curto em português do Brasil, PENSADO PRA SER FALADO EM VOZ ALTA \
(não lido), dividido em 3 partes, mais o nome do jogo principal da notícia:

- "hook": uma frase de abertura (máximo 12 palavras) que já entra com \
energia máxima nos primeiros 2 segundos — grito de empolgação, reação \
genuína, ou afirmação bombástica que entrega o que promete. Nada de \
introdução morna tipo "hoje vamos falar sobre".
- "body": o fato principal da notícia, em 2 a 4 frases BEM curtas e \
FLUIDAS, como se você estivesse contando pra um amigo, cheio de energia. \
Use pontuação que ajuda a voz soar mais viva: exclamações (!), reticências \
para pausa dramática (...), frases curtas ao invés de uma frase longa e \
complexa. Use contrações naturais da fala brasileira ("tá", "pra", "cê", \
"né", "bora") quando fizer sentido, sem exagerar a ponto de virar gíria \
regional forçada. Nunca invente informação que não está na fonte.
- "cta": uma chamada final curta (máximo 10 palavras), empolgada, pedindo \
engajamento (comentar, seguir, compartilhar) ou fazendo uma pergunta \
provocativa pro público.
- "game_name": o nome oficial e completo do jogo principal mencionado na \
notícia (ex: "Forza Horizon 6", "Grand Theft Auto VI"), em inglês, do jeito \
que apareceria em uma busca por trailer oficial. Se a notícia não for sobre \
um jogo específico (ex: notícia de indústria/empresa), use string vazia "".

Regras importantes:
- NUNCA invente fatos, datas ou detalhes que não estão no texto fonte.
- Se a notícia for um rumor/leak não confirmado, deixe isso claro no roteiro \
("segundo rumores...", "ainda não confirmado...") — mas mantendo a energia.
- Tom: MUITO empolgado e genuíno, nunca sensacionalista a ponto de distorcer \
o fato, e nunca formal/robótico. Pense em como um criador de conteúdo de \
games realmente fala, não como um texto escrito para ser lido.
- Frases curtas > frase longa. Ritmo rápido > explicação arrastada.
- Português do Brasil, 100% natural e falado, nunca em registro formal/escrito.

Responda APENAS com um JSON válido no formato:
{"hook": "...", "body": "...", "cta": "...", "game_name": "..."}
Sem markdown, sem texto antes ou depois do JSON, sem explicações.
"""


class ScriptGenError(RuntimeError):
    pass


def _run_claude_cli(prompt: str, timeout: int = 60) -> str:
    """Executa `claude -p <prompt>` como subprocess, sem ANTHROPIC_API_KEY no
    ambiente (para forçar uso do login OAuth da assinatura Pro/Max).
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    if result.returncode != 0:
        raise ScriptGenError(
            f"claude CLI falhou (exit {result.returncode}): {result.stderr.strip()[:500]}"
        )

    return result.stdout.strip()


def generate_script(
    title: str,
    summary: str,
    source: str,
    model: str = DEFAULT_MODEL,
    runner=None,
) -> dict:
    """Gera um roteiro {hook, body, cta} em português a partir de uma notícia,
    via `claude -p` (assinatura Pro/Max do usuário).

    `runner` pode ser injetado para testes (callable(prompt) -> str); se
    omitido, usa o subprocess real do CLI.
    """
    runner = runner or _run_claude_cli

    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Fonte: {source}\n"
        f"Título: {title}\n"
        f"Resumo: {summary or '(sem resumo disponível, use apenas o título)'}"
    )

    raw_text = runner(full_prompt)
    return _parse_script_json(raw_text)


def _parse_script_json(raw_text: str) -> dict:
    """Parseia o JSON retornado pelo modelo, tolerando cercas de código markdown
    e texto extra antes/depois do objeto JSON.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            if first_line.strip().lower() in ("json", ""):
                text = rest

    text = text.strip()

    # Se ainda houver texto ao redor, extrai o primeiro objeto JSON válido.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    data = json.loads(text)

    for field in ("hook", "body", "cta"):
        if field not in data or not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"Campo '{field}' ausente ou vazio no roteiro gerado: {data}")

    game_name = data.get("game_name", "")
    if not isinstance(game_name, str):
        game_name = ""

    return {
        "hook": data["hook"].strip(),
        "body": data["body"].strip(),
        "cta": data["cta"].strip(),
        "game_name": game_name.strip(),
    }
