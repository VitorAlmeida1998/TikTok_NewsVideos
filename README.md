# TikTok News Videos — Pipeline de Notícias de Games

Pipeline automatizado que monitora notícias internacionais de games em tempo
real, filtra as mais relevantes, gera um roteiro em português via LLM,
transforma em vídeo curto (narração + legendas + imagens) e publica no
TikTok — com o objetivo de captar e transformar a notícia em conteúdo antes
que o público brasileiro veja em outro lugar.

## Como funciona (pipeline)

```
 feeds RSS  →  collector  →  dedupe  →  script_gen  →  video_gen  →  publisher
(IGN, etc.)   (coleta e     (filtro    (roteiro PT-BR   (TTS +      (posta no
              normaliza)    de         via LLM)         legendas +  TikTok)
                            relevância)                 imagens)
```

Cada etapa é um módulo Python independente, testável isoladamente, que lê e
escreve no mesmo banco SQLite compartilhado (`data/news.db`).

| Módulo | Status | Descrição |
|---|---|---|
| `collector` | ✅ pronto | Coleta feeds RSS, normaliza e salva com dedupe por hash |
| `dedupe` | ✅ pronto | Filtro de relevância por palavras-chave |
| `script_gen` | 🚧 planejado | Roteiro em PT-BR via API Anthropic |
| `video_gen` | 🚧 planejado | TTS + legendas + imagens (Remotion) |
| `publisher` | 🚧 planejado | Publicação automática no TikTok |

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) para gerenciamento de dependências

## Setup

```bash
git clone https://github.com/VitorAlmeida1998/TikTok_NewsVideos.git
cd TikTok_NewsVideos
uv sync
cp .env.example .env   # preencher chaves de API quando necessário
```

## Uso

### 1. Coletar notícias

Lê os feeds configurados em `feeds.yaml`, normaliza cada item e salva no
SQLite (dedupe automático por título+URL):

```bash
uv run python -m collector.run
```

Feeds padrão: IGN, Kotaku, GamesIndustry.biz, PC Gamer, Eurogamer. Edite
`feeds.yaml` para adicionar/remover fontes.

### 2. Filtrar por relevância

Avalia os itens ainda não avaliados e marca quais são relevantes com base
em palavras-chave (leak, reveal, delay, launch, exclusive, trailer, release
date, confirmed...). Idempotente — não reprocessa itens já avaliados:

```bash
uv run python -m dedupe.run
```

### Rodando via cron

```cron
*/10 * * * * cd /caminho/do/projeto && uv run python -m collector.run >> logs/collector.log 2>&1
*/10 * * * * cd /caminho/do/projeto && uv run python -m dedupe.run    >> logs/dedupe.log    2>&1
```

## Estrutura do projeto

```
/collector       -> coleta de RSS/APIs de notícias
/dedupe          -> deduplicação e filtro de relevância
/script_gen      -> geração de roteiro via LLM (Anthropic API)
/video_gen       -> geração de vídeo (TTS + legendas + imagens)
/publisher       -> integração com API de publicação no TikTok
/shared          -> modelos de dados (NewsItem), acesso ao SQLite, configs
/tests           -> testes por módulo, espelhando a estrutura acima
feeds.yaml       -> lista de feeds RSS monitorados
.env.example     -> template de variáveis de ambiente (sem valores reais)
CLAUDE.md        -> especificação detalhada do projeto e convenções
```

## Testes

```bash
uv run pytest -v
```

Todos os testes rodam 100% offline (fixtures locais, SQLite em diretório
temporário) — nenhuma chamada de rede é feita durante `pytest`.

## Stack

- **Linguagem:** Python 3.12+
- **Dependências:** uv
- **Banco de dados:** SQLite (dedupe e histórico)
- **Coleta:** feedparser (RSS/Atom)
- **Orquestração:** scripts Python + cron (sem Airflow/n8n nesta fase)
- **Testes:** pytest
- **Vídeo (planejado):** Remotion (self-hosted) + TTS (ElevenLabs/OpenAI) +
  whisper.cpp para legendas sincronizadas

## Regras e convenções

- Nunca commitar chaves de API, tokens ou credenciais — sempre via `.env`
  (git-ignorado), com `.env.example` documentando as variáveis esperadas
- Cada módulo é testável isoladamente, com baixo acoplamento entre coleta,
  geração e publicação
- Ao gerar vídeo, nunca usar imagens/prints de sites de notícias de
  terceiros — apenas capturas do próprio jogo ou material oficial de
  divulgação, para evitar strike de copyright
- Antes de automatizar a publicação, validar manualmente pelo menos 5
  vídeos gerados ponta a ponta

Detalhes completos de especificação e decisões de arquitetura em
[`CLAUDE.md`](./CLAUDE.md).

## Licença

Projeto pessoal — sem licença definida ainda.
