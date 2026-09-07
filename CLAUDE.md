# Pipeline Automatizado de Notícias de Games → TikTok

Pipeline que monitora fontes internacionais de notícias de games em tempo real,
filtra/deduplica, gera roteiro em português via LLM, transforma em vídeo curto
e publica no TikTok — buscando vantagem de velocidade sobre o ciclo de
notícias BR.

## Stack

- Python 3.12, gerenciado com `uv`
- SQLite para dedupe/histórico
- Scripts Python simples + cron (sem orquestrador nesta fase)
- pytest para testes

## Estrutura

```
/collector       -> coleta de RSS/APIs de notícias            [FEITO]
/dedupe          -> deduplicação e filtro de relevância        [TODO]
/script_gen      -> geração de roteiro via LLM (Anthropic)     [TODO]
/video_gen       -> TTS + legendas + imagens                   [TODO]
/publisher       -> integração com TikTok                      [TODO]
/shared          -> modelos de dados, configs, utils comuns
/tests           -> testes por módulo, espelhando a estrutura acima
```

## Setup

```bash
uv sync
cp .env.example .env   # preencher chaves quando necessário
```

## Módulo 1: Collector (concluído)

Lê feeds RSS configurados em `feeds.yaml`, normaliza cada item em um
`NewsItem` (shared/models.py) e salva no SQLite (`data/news.db`) com dedupe
automático via hash de título+URL.

Rodar coleta manualmente:

```bash
uv run python -m collector.run
# ou com paths customizados:
uv run python -m collector.run --feeds feeds.yaml --db data/news.db
```

Feeds atualmente configurados: IGN, Kotaku, GamesIndustry.biz, PC Gamer,
Eurogamer (editar `feeds.yaml` para adicionar/remover).

Rodar via cron (a cada 10 min, exemplo):

```
*/10 * * * * cd /home/vitor/Tiktok-GameNews && /home/vitor/.hermes/bin/uv run python -m collector.run >> logs/collector.log 2>&1
```

### Arquivos

- `collector/feeds_config.py` — carrega `feeds.yaml`
- `collector/parser.py` — busca (`fetch_feed`) e parseia (`parse_feed`) feeds via `feedparser`
- `collector/run.py` — orquestra: lê feeds, parseia, salva no banco (CLI)
- `shared/models.py` — dataclass `NewsItem` com `content_hash` para dedupe
- `shared/db.py` — conexão SQLite, schema, `save_item(s)`, `item_exists`

## Testes

```bash
uv run pytest -v
```

14 testes, todos offline (fixture local em `tests/fixtures/sample_feed.xml`,
banco SQLite em `tmp_path`, sem chamadas de rede).

## Próximo módulo: Dedupe

Hash de título/URL (já implementado em `NewsItem.content_hash` + dedupe no
`save_item`) + filtro por palavras-chave de relevância (leak, reveal, delay,
launch, exclusive).

## Regras

- Nunca commitar chaves/tokens — sempre via `.env` (git-ignorado)
- Cada módulo testável isoladamente
- Vídeo: nunca usar imagens de sites de notícias de terceiros — só capturas
  do próprio jogo ou material oficial de divulgação
- Validar manualmente pelo menos 5 vídeos ponta a ponta antes de automatizar
  a publicação
