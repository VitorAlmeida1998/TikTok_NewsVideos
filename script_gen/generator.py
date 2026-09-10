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

Por que o formato de resposta NÃO é JSON:
- Notícias de games frequentemente têm aspas no próprio título/resumo
  (falas citadas, ex: '"Rockstar has tried to get away with..."'). Quando
  o modelo ecoa esse tipo de conteúdo dentro de uma string JSON sem escapar
  a aspas internamente, o JSON gerado fica inválido e o parse quebra
  (json.JSONDecodeError). Em vez de brigar com escaping, cada campo é
  identificado por um marcador de linha (ex: "HOOK:") e o valor vai até o
  próximo marcador — aspas, apóstrofos etc. dentro do texto não têm nenhum
  significado especial nesse formato, então não têm como quebrar o parser.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess

logger = logging.getLogger("script_gen")

DEFAULT_MODEL = "claude-cli"  # marcador; o modelo real é decidido pela assinatura/CLI

FIELD_NAMES = ["HOOK", "BODY", "CTA", "DESCRIPTION", "GAME_NAME", "PRONUNCIATIONS"]

SYSTEM_PROMPT = """\
Você é um criador de conteúdo brasileiro, do tipo que grava vídeo curto de \
games pro TikTok falando direto pra câmera, com MUITA empolgação e energia \
de verdade — tipo hypado, envolvido, nunca robótico ou de "apresentador de \
telejornal". Seu público é jovem, gamer, já cansado de vídeo sem graça, e \
rola o feed em menos de 1 segundo se não for fisgado na hora.

Você recebe uma notícia de games em inglês (título + resumo) e deve gerar \
um roteiro curto em português do Brasil, PENSADO PRA SER FALADO EM VOZ ALTA \
(não lido), otimizado pra reter atenção do primeiro ao último segundo — \
mais a descrição de publicação e o nome do jogo principal da notícia:

- HOOK: uma frase de abertura (máximo 12 palavras) que cria uma LACUNA DE \
CURIOSIDADE — dá informação suficiente pra fisgar, mas segura o detalhe \
mais importante/surpreendente pro corpo, forçando quem assiste a continuar \
pra descobrir o resto. Formatos que funcionam: afirmação bombástica sem o \
"porquê" ainda ("Isso muda TUDO no [jogo]..."), pergunta que o público \
precisa saber a resposta, contraste/reviravolta ("Todo mundo achava X, mas \
não é isso que aconteceu"), ou número/ranking chamativo. NUNCA entregue o \
fato principal já no hook — isso mata a razão de continuar assistindo. \
Nada de introdução morna tipo "hoje vamos falar sobre".
- BODY: o fato principal da notícia, em 2 a 4 frases BEM curtas e \
FLUIDAS, como se você estivesse contando pra um amigo, cheio de energia. \
Estruture como uma escalada: primeiro contexto rápido, depois vai \
aumentando a tensão/expectativa, e guarda o detalhe mais chocante/relevante \
pra frase final do corpo (o "pagamento" da lacuna aberta no hook) — isso \
segura quem ia sair no meio. Use pontuação que ajuda a voz soar mais viva: \
exclamações (!), reticências para pausa dramática (...), frases curtas ao \
invés de uma frase longa e complexa. Use contrações naturais da fala \
brasileira ("tá", "pra", "cê", "né", "bora") quando fizer sentido, sem \
exagerar a ponto de virar gíria regional forçada. Nunca invente informação \
que não está na fonte.
- CTA: uma chamada final curta (máximo 12 palavras), empolgada, escolhendo \
UM dos três modos abaixo conforme o tipo de notícia (nunca um "curte e \
compartilha" genérico sem motivo nenhum por trás):
  (1) PUXAR COMENTÁRIO — pergunta de opinião, previsão ou "time A ou time \
  B". Ideal pra rumor/leak/polêmica, porque comentário é o sinal de \
  engajamento mais forte pra um vídeo ser empurrado pra mais gente.
  (2) PEDIR PRA SEGUIR — usando a vantagem de velocidade como motivo real \
  pra seguir, tipo "segue aqui que a próxima sai antes de todo mundo saber" \
  (adapte a frase, não repita sempre igual). Ideal pra notícia grande ou \
  confirmada, onde o furo em si já é a atração.
  (3) MARCAR UM AMIGO — "manda pra aquele amigo que..." / "marca quem \
  precisa saber disso", nomeando o TIPO de pessoa (o fã da franquia, quem \
  tá juntando dinheiro pro console, quem comprou no lançamento). Envio por \
  DM é o sinal que mais espalha vídeo pra fora da bolha. Ideal pra data de \
  lançamento, preço, promoção/de graça, atraso, ou qualquer notícia que \
  afeta uma decisão de compra/tempo de alguém.
  Varie entre os três modos ao longo dos vídeos; não use o mesmo sempre.
- DESCRIPTION: a legenda que vai junto do vídeo na publicação do TikTok, \
pensada pra alcance/descoberta (não é falada, só lida). Estrutura: (1) uma \
frase curta com as palavras-chave principais da notícia logo no início \
(nome do jogo + assunto) — o TikTok indexa a legenda pra busca, então \
palavra-chave relevante no começo ajuda o vídeo aparecer em pesquisas; (2) \
opcionalmente uma segunda frase curta de gancho/opinião; (3) de 4 a 6 \
hashtags misturando amplitude e nicho: 1-2 amplas de descoberta (ex: #fyp, \
#viral, #foryoupage), 1-2 de comunidade gamer (ex: #gaming, #gamer, \
#tiktokgaming, #gamertok), e 1-2 específicas do jogo/franquia/assunto (ex: \
#gta6, #nomedojogo, #gamenews, #leak — o que for mais preciso pro caso). \
O público é BRASILEIRO: inclua pelo menos 1 hashtag em português que o \
brasileiro realmente busca (#games, #jogos, #noticiasdegames, #gamesbr, \
#vazou — a que couber), e use na primeira frase a palavra que a pessoa \
digitaria na busca (ex: "vazou", "data de lançamento", "de graça", \
"atrasado"). Hashtag NUNCA tem espaço nem acento (#leonkennedy, não \
"#leon kennedy"). Nunca encha de hashtag genérica demais a ponto de virar \
spam (isso reduz alcance, não aumenta) — hashtag tem que ser sempre \
relevante ao conteúdo real da notícia.
- GAME_NAME: o nome oficial e completo do jogo principal mencionado na \
notícia (ex: Forza Horizon 6, Grand Theft Auto VI), em inglês, do jeito \
que apareceria em uma busca por trailer oficial. Se a notícia não for sobre \
um jogo específico (ex: notícia de indústria/empresa), deixe em branco.
- PRONUNCIATIONS: lista de termos em INGLÊS que aparecem no HOOK/BODY/CTA \
(nomes de jogos, estúdios, consoles, termos como "early access") com o \
respelling fonético de como um brasileiro fala esse termo em inglês, em \
ortografia portuguesa com acento na sílaba tônica — vai ser usado só pela \
voz sintética (as legendas mostram o termo original). Formato: \
"Termo=respelling; Outro termo=respelling". Ex: "Wolverine=Uólverin; \
Kingdom Hearts=Kíngdom Rárts; early access=érli ácsess". Inclua todos os \
termos em inglês do roteiro, exceto os que já são lidos naturalmente em \
português (ex: PlayStation, Xbox, Nintendo, Steam, Switch). Se não houver \
nenhum, deixe em branco.

Regras importantes:
- NUNCA invente fatos, datas ou detalhes que não estão no texto fonte — a \
lacuna de curiosidade do hook é sobre ORDEM DE REVELAÇÃO da informação real, \
nunca sobre inventar um fato que não existe na fonte só pra gerar suspense.
- Se a notícia for um rumor/leak não confirmado, deixe isso claro no roteiro \
("segundo rumores...", "ainda não confirmado...") — mas mantendo a energia.
- Tom: MUITO empolgado e genuíno, nunca sensacionalista a ponto de distorcer \
o fato, e nunca formal/robótico. Pense em como um criador de conteúdo de \
games realmente fala, não como um texto escrito para ser lido.
- Frases curtas > frase longa. Ritmo rápido > explicação arrastada.
- Português do Brasil, 100% natural e falado no HOOK/BODY/CTA; a \
DESCRIPTION pode ser texto escrito normal (é legenda, não é falada).
- Pode usar aspas, apóstrofos e qualquer pontuação livremente dentro de \
cada campo — não tem problema nenhum, o formato de resposta não usa aspas \
como delimitador.

Responda SEMPRE nesse formato exato, com cada campo em uma linha começando \
pelo nome do campo em maiúsculas seguido de dois-pontos — nada de JSON, \
nada de markdown, nada de texto antes ou depois:

HOOK: texto do hook aqui
BODY: texto do corpo aqui
CTA: texto do cta aqui
DESCRIPTION: texto da legenda com hashtags aqui
GAME_NAME: nome do jogo aqui (ou deixe em branco depois dos dois-pontos)
PRONUNCIATIONS: Termo=respelling; Outro=respelling (ou em branco)
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
    recent_hooks: list[str] | None = None,
) -> dict:
    """Gera um roteiro {hook, body, cta, description, game_name, pronunciations} em português
    a partir de uma notícia, via `claude -p` (assinatura Pro/Max do usuário).

    `runner` pode ser injetado para testes (callable(prompt) -> str); se
    omitido, usa o subprocess real do CLI.
    """
    runner = runner or _run_claude_cli

    # Aberturas recentes vão no prompt para o canal não virar um template só
    # ("GENTE," em 6 dos 19 primeiros vídeos) — repetição cansa o público e
    # faz o feed inteiro parecer o mesmo vídeo.
    avoid_block = ""
    if recent_hooks:
        listed = "\n".join(f"- {hook}" for hook in recent_hooks[:10])
        avoid_block = (
            "\n\nEstes foram os hooks dos vídeos mais recentes deste canal. "
            "NÃO comece o novo hook com a mesma palavra nem repita a mesma "
            "estrutura de nenhum deles — varie a forma de fisgar:\n" + listed
        )

    full_prompt = (
        f"{SYSTEM_PROMPT}{avoid_block}\n\n"
        f"Fonte: {source}\n"
        f"Título: {title}\n"
        f"Resumo: {summary or '(sem resumo disponível, use apenas o título)'}"
    )

    raw_text = runner(full_prompt)
    return _parse_script_response(raw_text)


# Depois dos dois-pontos só consome espaço/tab (não \n): um campo vazio seguido
# de outro campo na linha de baixo tem que ficar vazio, não engolir o próximo.
_FIELD_PATTERN = re.compile(
    r"(?:^|\n)\s*(" + "|".join(FIELD_NAMES) + r")\s*:[ \t]*(.*?)"
    r"(?=\n\s*(?:" + "|".join(FIELD_NAMES) + r")\s*:|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_script_response(raw_text: str) -> dict:
    """Parseia a resposta do modelo no formato "CAMPO: valor" (um por linha,
    valor pode se estender por várias linhas até o próximo campo).

    Tolerante a cercas de código markdown ao redor da resposta inteira.
    Não usa JSON de propósito — ver docstring do módulo.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json") or text.lower().startswith("text"):
            text = text.split("\n", 1)[1] if "\n" in text else ""

    matches = _FIELD_PATTERN.findall(text)
    data: dict[str, str] = {}
    for label, value in matches:
        key = label.upper()
        # Colapsa quebras de linha internas (campos são texto contínuo).
        data[key] = re.sub(r"\s+", " ", value).strip()

    for field in ("HOOK", "BODY", "CTA"):
        if not data.get(field):
            raise ValueError(
                f"Campo '{field}' ausente ou vazio na resposta do modelo: {raw_text[:500]!r}"
            )

    return {
        "hook": data["HOOK"],
        "body": data["BODY"],
        "cta": data["CTA"],
        "description": data.get("DESCRIPTION", ""),
        "game_name": data.get("GAME_NAME", ""),
        "pronunciations": data.get("PRONUNCIATIONS", ""),
    }
