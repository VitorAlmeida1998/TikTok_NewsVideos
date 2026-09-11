# Projeto: Pipeline Automatizado de Notícias de Games → TikTok

## Status: COMPLETO — todas as 5 etapas implementadas e validadas com dados reais

## Objetivo

Pipeline que:
1. Monitora fontes internacionais de notícias de games em tempo real
2. Filtra e deduplica notícias relevantes
3. Gera um roteiro curto em português usando IA
4. Transforma o roteiro em um vídeo curto (narração + legendas + imagens)
5. Publica automaticamente no TikTok

Vantagem de velocidade: captar e transformar em conteúdo antes que o público
BR veja a notícia em outro lugar.

## Stack (final)

- **Linguagem**: Python 3.12+, gerenciado com uv
- **Banco de dados**: SQLite (dedupe, histórico, estado de cada etapa)
- **Orquestração**: scripts Python (`pipeline/run.py` roda tudo) + cron do
  sistema (instalado, `*/30 * * * *`, dry-run)
- **Testes**: pytest, 65 testes, 100% offline
- **Roteiro (script_gen)**: Claude Code CLI (`claude -p`) via subprocess,
  usa a assinatura Claude Pro/Max do usuário — NÃO usa a API paga por
  token (`ANTHROPIC_API_KEY` é removida do ambiente do subprocess para
  forçar login OAuth). Decisão tomada porque a API key paga estava sem
  crédito e o usuário tem assinatura Pro. Prompt tunado para gerar texto
  falado (não escrito): frases curtas, exclamações, reticências para
  pausa dramática, contrações da fala brasileira ("tá", "pra", "cê") —
  pensado pra soar como criador de conteúdo empolgado, não texto lido.
- **TTS (video_gen)**: ElevenLabs (`eleven_multilingual_v2`), com
  `voice_settings` tunados para expressividade: `stability=0.3` (mais
  variação emocional), `style=0.65` (amplifica expressividade natural da
  voz), `speed=1.08` (ritmo mais ágil). Voz configurável via
  `ELEVENLABS_VOICE_ID` no `.env` sem precisar mexer em código.
- **Legendas (video_gen)**: timestamps por palavra vêm do alinhamento por
  caractere do próprio ElevenLabs (`convert_with_timestamps`), mapeado de
  volta pras palavras originais do roteiro (`video_gen/alignment.py`). O
  whisper foi removido: legendas agora têm o texto exato do roteiro.
- **Pronúncia de termos em inglês (video_gen/pronunciation.py)**: respelling
  fonético só no texto enviado ao TTS ("Wolverine" -> "Uólverin"); fontes:
  `pronunciations.yaml` (global, vence) + campo PRONUNCIATIONS gerado pelo
  script_gen por notícia (`script_pronunciations`).
- **Capa (thumbnail)**: `video_gen/cover.py` + composição `NewsCover`
  (renderizada com `remotion still --frame=N`, N = 25% do clipe de fundo).
  `generate_video_for_item` devolve `cover_path` quando dá certo; falha de
  capa nunca invalida o vídeo.
- **Travas de custo**: `video_gen/quota.py` (lê a assinatura do ElevenLabs)
  + `max_videos_per_day`/`tts_reserve_chars` em settings, aplicados em
  `video_gen/run.py`. Motivo: o monitor roda a cada 2 min e a fila é sempre
  maior que a cota (~82 narrações/mês no plano Starter).
- **Configurações de runtime**: `shared/settings.py` -> `data/settings.json`
  (voz do TTS, nome/iniciais do canal, horários de pico, posts por dia,
  limiar de "notícia quente"). O painel edita; o TTS resolve a voz por
  chamada (troca vale no próximo vídeo, sem reiniciar).
- **Fila de publicação**: `publisher/schedule.py` (`build_schedule`) dá
  horário de pico BR a cada vídeo pronto, ou marca "postar agora" pra
  notícia quente+fresca. `pipeline/watch.py` chama isso ao fim de cada
  ciclo; o painel mostra em `/publicar`. Upload continua manual — NUNCA
  automatizar via GUI do app do TikTok (proibido pelos Termos; risco de ban).
- **Uma história, um vídeo**: `dedupe/story_group.py` agrupa por
  similaridade de título (Jaccard, janela de 36h) e `shared/db.py` filtra a
  fila com `_NO_DUPLICATE_STORY`.
- **Frescor**: `EFFECTIVE_SCORE_SQL` (db) e `freshness_multiplier`
  (keyword_filter) — a fila ordena por relevância x frescor, não pelo score
  congelado.
- **Modo autônomo (cron)**: `--require-media` (só renderiza com fundo +
  música; senão marca `video_skip_reason` = "aguardando mídia" no painel,
  sem gastar TTS), `--max-age-hours 48`, fila ordenada por
  `relevance_score` (dedupe/keyword_filter.relevance_score). Quem roda de
  verdade é o monitor contínuo `pipeline/watch.py` (polling dos feeds a
  cada 2 min, subido por `scripts/watcher.sh`; cron `*/5` é só watchdog via
  flock). Clipes/OST do YouTube são cortados a partir de 45% da duração
  (`MIDDLE_START_FRACTION`), nunca do início.
- **Vídeo (video_gen)**: Remotion (React/TS, projeto Node.js em
  `video_gen/remotion/`), formato 1080x1920, renderizado via
  `npx remotion render` chamado por subprocess. Assets de áudio/vídeo de
  fundo precisam estar dentro de `remotion/public/` (staticFile()) — paths
  absolutos do filesystem NÃO funcionam diretamente no render do Remotion.
- **Gameplay de fundo (video_gen)**: ordem de prioridade — (1) clipe manual
  do usuário em `video_gen/manual_clips/<slug>.*`, processado/cacheado na
  primeira vez (`_prepare_manual_clip`); (2) cache automático em
  `data/gameplay_cache/<slug>.mp4`; (3) `yt-dlp` busca "<jogo> official
  trailer" no YouTube, baixa trecho curto (~12s, 1080p) via
  `--download-sections`, recorta/escala pra 9:16 com ffmpeg. Requer runtime
  `deno` instalado. Fallback final: fundo gradiente.
  **REGRA DURA: nunca contornar verificação de idade/login do YouTube**
  (sem cookies de sessão, sem conta automatizada, sem nenhum método de
  burlar esse gate) — usuário perguntou explicitamente sobre isso e a
  resposta foi recusar e implementar o sistema de clipes manuais como
  alternativa segura em vez disso.
- **Publisher**: TikTok Content Posting API v2 (`open.tiktokapis.com`),
  modo inbox (draft, padrão) ou direct post. Dry-run por padrão.

## Estrutura do projeto (final)

```
/collector       -> coleta de RSS/APIs de notícias            [FEITO]
/dedupe          -> deduplicação e filtro de relevância        [FEITO]
/script_gen      -> geração de roteiro via Claude CLI (PT-BR)   [FEITO]
/video_gen       -> TTS + legendas + render Remotion            [FEITO]
  /remotion      -> projeto Node.js/React, template do vídeo
/publisher       -> integração com TikTok Content Posting API   [FEITO]
/pipeline        -> orquestrador end-to-end                     [FEITO]
/shared          -> modelos de dados, configs, utils comuns, SQLite
/tests           -> 65 testes, espelhando a estrutura acima
.env             -> chaves de API (NUNCA commitar; git-ignorado)
.env.example     -> template sem valores reais
feeds.yaml       -> feeds RSS monitorados
CLAUDE.md        -> este arquivo
```

## Módulo 1: Collector

Lê `feeds.yaml`, busca e parseia via `feedparser`, normaliza em `NewsItem`
(shared/models.py), salva no SQLite com dedupe por hash de título+URL
(shared/db.py). CLI: `uv run python -m collector.run`.

## Módulo 2: Dedupe

Filtro de relevância por palavras-chave (leak, reveal, delay, launch,
exclusive, trailer, release date, confirmed...) em `dedupe/keyword_filter.py`.
Avalia apenas itens com `is_relevant IS NULL` (idempotente). CLI:
`uv run python -m dedupe.run`.

## Módulo 3: Script Gen

`script_gen/generator.py`: monta um prompt (system prompt + título + resumo
+ fonte) e chama `claude -p` via subprocess (`_run_claude_cli`), removendo
`ANTHROPIC_API_KEY` do ambiente do subprocess para garantir uso do login
OAuth da assinatura Pro/Max em vez de billing por API. Parseia a resposta
como JSON `{"hook", "body", "cta"}`, tolerando cercas markdown e texto
extra ao redor do JSON.

`script_gen/run.py`: busca itens relevantes sem roteiro
(`get_items_pending_script`), gera e salva (`save_script`). CLI:
`uv run python -m script_gen.run --limit N`.

**Pitfall resolvido**: inicialmente implementado com SDK `anthropic`
(API paga por token) — a conta do usuário estava sem crédito
("Your credit balance is too low"). Usuário tem assinatura Claude Pro,
que dá acesso ao `claude` CLI via OAuth mas NÃO créditos de API separados.
Solução: usar `claude -p` como subprocess, removendo `ANTHROPIC_API_KEY`
do ambiente (que teria prioridade sobre o login OAuth se presente).

## Módulo 4: Video Gen

- `video_gen/tts.py`: ElevenLabs `text_to_speech.convert()`, streaming para
  arquivo MP3. Requer `ELEVENLABS_API_KEY` com permissão `text_to_speech`
  habilitada na dashboard (erro 401 "missing_permissions" se não habilitada
  — não é erro de chave inválida).
- `video_gen/alignment.py`: `WordTiming(word, start, end)` a partir do
  alinhamento por caractere do ElevenLabs + spans de `pronunciation.py`.
- `video_gen/assembler.py`: monta a narração (hook+body+cta), gera áudio,
  transcreve, copia o áudio pra `video_gen/remotion/public/audio/` (Remotion
  só serve assets de dentro de `public/` via `staticFile()`), monta o spec
  JSON (`data/video_specs/item_N.json`), chama
  `npx remotion render NewsShort <output> --props=<spec>`.
- `video_gen/remotion/`: projeto Node.js/React independente.
  - `src/NewsShort.tsx`: componente do vídeo — fundo gradiente, hook
    animado no topo, legendas "karaokê" palavra-a-palavra (janela de 4
    palavras, palavra ativa em amarelo com leve scale, `display: inline-block`
    + `padding` para não colar palavras vizinhas — bug já corrigido), CTA
    aparece perto do fim (calculado dinamicamente).
  - `src/Root.tsx`: composição 1080x1920, `calculateMetadata` ajusta a
    duração do vídeo dinamicamente com base no fim da última palavra
    transcrita + 1.5s de tail (não usa duração fixa).
  - Schema via `zod` (versão pinada em `4.5.4` — importante manter em sync
    com a versão do pacote `remotion`, senão dá warning/quebra silenciosa).
- `video_gen/run.py`: busca itens com roteiro sem vídeo
  (`get_items_pending_video`), gera, salva (`save_video`). CLI:
  `uv run python -m video_gen.run --limit N [--no-render]`.

**Validado com dados reais**: 5 vídeos MP4 1080x1920 gerados e inspecionados
visualmente (via vision_analyze em frames extraídos com ffmpeg) — narração,
legendas sincronizadas e CTA funcionando corretamente.

## Módulo 5: Publisher

`publisher/tiktok_client.py`: cliente para TikTok Content Posting API v2.
- `post_video_to_inbox()`: modo draft — vídeo vai pra caixa de entrada do
  TikTok do usuário, que revisa e publica manualmente no app. Padrão, mais
  seguro (escopo `video.upload`).
- `post_video_direct()`: publica direto no perfil (escopo `video.publish`,
  aprovação mais rigorosa do TikTok).
- Fluxo: POST `.../video/init/` (retorna `publish_id` + `upload_url`) → PUT
  do vídeo em chunk único pra `upload_url` → (opcional) GET
  `.../status/fetch/` pra acompanhar processamento.
- `check_publish_status()`: consulta status de um `publish_id`.

`publisher/run.py`: CLI com **dry-run como padrão** (`--dry-run` é o
default; precisa passar `--live` explicitamente pra publicar de verdade).
Busca itens com vídeo pronto não publicados (`get_items_pending_publish`),
processa, salva resultado (`save_publish_result`).

**Bloqueio conhecido**: publicar de verdade requer app registrado em
developers.tiktok.com com "Content Posting API" aprovado pela TikTok
(revisão manual, pode levar dias) + fluxo OAuth2 completo pra obter
`TIKTOK_ACCESS_TOKEN`. Usuário ainda não tem isso — código pronto e testado,
aguardando credenciais.

## Módulo 6: Pipeline (orquestrador end-to-end)

`pipeline/run.py`: roda as 5 etapas em sequência com um único comando.
CLI: `uv run python -m pipeline.run --limit N [--publish-live] [--publish-mode inbox|direct] [--no-render]`.
Cron instalado no sistema: `*/30 * * * *`, `--limit 5`, dry-run (ver
`crontab -l`), logs em `logs/pipeline.log`.

## Testes

```bash
uv run pytest -v
```

65 testes, 100% offline. Mocks para: cliente ElevenLabs, WhisperModel,
runner do `claude` CLI, `requests.Session` do TikTok, cada etapa do
pipeline (nos testes do orquestrador end-to-end).

## Regras

- Nunca commitar chaves/tokens — sempre via `.env` (git-ignorado)
- Cada módulo testável isoladamente
- Vídeo: nunca usar imagens de sites de notícias de terceiros — só capturas
  do próprio jogo ou material oficial de divulgação (template atual usa
  fundo gradiente + texto, sem mídia externa — seguro por padrão)
- Publicação sempre em dry-run por padrão
- Validar manualmente pelo menos 5 vídeos ponta a ponta antes de automatizar
  a publicação — **CUMPRIDO**: 5 vídeos gerados e inspecionados visualmente

## Próximos passos possíveis (não bloqueantes, melhorias futuras)

- Adicionar B-roll/imagens de jogos (capturas próprias/material oficial) ao
  template Remotion, em vez de só fundo gradiente + texto
- Obter aprovação TikTok Content Posting API para publicar de verdade
- Adicionar mais fontes RSS
- Rate limiting / agendamento mais inteligente para não postar tudo de uma vez
- Fine-tuning do prompt do script_gen com base em performance real dos vídeos
