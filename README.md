# TikTok News Videos — Pipeline de Notícias de Games

Pipeline automatizado, **completo e funcional**, que monitora notícias
internacionais de games em tempo real, filtra as mais relevantes, gera um
roteiro em português via IA, transforma em vídeo curto (narração + legendas
sincronizadas + visual) e prepara para publicação no TikTok — com o
objetivo de captar e transformar a notícia em conteúdo antes que o público
brasileiro veja em outro lugar.

## Status: pipeline completo, validado ponta a ponta com dados reais

Todas as 5 etapas estão implementadas, testadas (65 testes automatizados) e
validadas com execução real (não apenas mocks): 290+ notícias coletadas,
roteiros gerados via IA, 5 vídeos MP4 1080x1920 renderizados com narração e
legendas sincronizadas.

```
 feeds RSS  →  collector  →  dedupe  →  script_gen  →  video_gen  →  publisher
(IGN, etc.)   (coleta e     (filtro    (roteiro PT-BR   (TTS +      (posta no
              normaliza)    de         via IA)          legendas +  TikTok,
                            relevância)                 imagens)    dry-run por padrão)
```

| Módulo | Status | Descrição |
|---|---|---|
| `collector` | ✅ pronto | Coleta feeds RSS, normaliza e salva com dedupe por hash |
| `dedupe` | ✅ pronto | Filtro de relevância por palavras-chave |
| `script_gen` | ✅ pronto | Roteiro em PT-BR via Claude Code CLI (assinatura Pro/Max) |
| `video_gen` | ✅ pronto | TTS (ElevenLabs, com timestamps por palavra + respelling de pronúncia) + render (Remotion) |
| `publisher` | ✅ pronto | TikTok Content Posting API — **dry-run por padrão**, requer app aprovado pra publicar de verdade |
| `pipeline` | ✅ pronto | Orquestrador end-to-end, todas as etapas em 1 comando |

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) para gerenciamento de dependências
- Node.js 18+ e npm (para renderização de vídeo via Remotion)
- ffmpeg (geralmente já presente no sistema)
- [deno](https://deno.land) (runtime JS usado pelo yt-dlp para extrair vídeos do YouTube corretamente)
- Claude Code CLI autenticado (`claude`) — usa sua assinatura Pro/Max para o `script_gen`, sem custo de API por token
- Conta ElevenLabs com permissão `text_to_speech` habilitada na API key

## Setup

```bash
git clone https://github.com/VitorAlmeida1998/TikTok_NewsVideos.git
cd TikTok_NewsVideos
uv sync
cp .env.example .env   # preencher ELEVENLABS_API_KEY (e TikTok, quando tiver)
cd video_gen/remotion && npm install && cd ../..
```

Note: `script_gen` usa o `claude` CLI (assinatura Pro/Max), **não** precisa
de `ANTHROPIC_API_KEY` — se essa variável estiver setada no ambiente, o
código a remove automaticamente antes de chamar o CLI, para forçar o uso do
login OAuth em vez de billing por API.

## Uso

### Pipeline completo (recomendado)

Roda todas as 5 etapas em sequência, com um único comando:

```bash
uv run python -m pipeline.run --limit 5
```

Por padrão, o `publisher` roda em **dry-run** (não publica nada de verdade,
só loga o que faria). Para publicar de verdade:

```bash
uv run python -m pipeline.run --limit 5 --publish-live --publish-mode inbox
```

### Rodando só a geração de vídeo, sem publisher (fluxo atual do usuário)

Quando o upload pro TikTok é feito manualmente (revisando os vídeos antes
de postar), use `--skip-publisher` para pular a etapa 5 completamente —
nem dry-run, nem chamada de API nenhuma:

```bash
uv run python -m pipeline.run --limit 5 --skip-publisher
```

### Modo autônomo (deixar o PC ligado e chegar com os vídeos prontos)

```bash
uv run python -m pipeline.run --limit 5 --skip-publisher --require-media --max-age-hours 48
```

- **Ranking de relevância**: o `dedupe` dá uma pontuação a cada notícia
  (peso das keywords — leak > exclusive/delay/release date > confirmed/reveal
  > launch/trailer, mais gatilhos de compartilhamento como free/price/
  cancelled/spoiler —, x1.5 se no título, bônus por franquia/plataforma de
  hype tipo GTA/Nintendo/Switch 2/Zelda, e peso por fonte). A ordem da fila
  usa **pontuação x frescor**: o valor decai com as horas desde a coleta
  (72h derrubam pra 15%), porque notícia de games perde a vantagem rápido.
  Roteiro e vídeo saem **do mais relevante pro menos**; `--limit` é por rodada.
- **Uma história, um vídeo**: cinco feeds cobrem o mesmo fato ("Forza
  atrasou no PS5" / "Forza NÃO atrasou"). O `dedupe` agrupa notícias
  parecidas numa janela de 36h (`story_group`, similaridade de título) e o
  pipeline só gera roteiro/vídeo para a primeira de cada história.
- `--max-age-hours 48`: ignora notícia velha (não gasta TTS com o que já
  passou).
- `--require-media`: só renderiza se o jogo tiver **vídeo de fundo E música**
  (cache, clipe manual ou download automático). Sem isso o item não gasta
  TTS e fica marcado como **"aguardando mídia"** no painel, com o motivo —
  você envia o fundo/música na página do item e a próxima rodada do cron
  gera o vídeo sozinha. O `--limit` conta vídeos gerados, não tentativas.
- Buscas no YouTube que falharem (ex: trailer com restrição de idade) não
  são repetidas por 24h (`data/*_cache/<slug>.unavailable`); a busca tenta
  os 5 primeiros resultados e fica com o primeiro que baixar. O trecho
  baixado começa a **45% da duração** do vídeo/faixa — nunca no começo, que
  em trailer é logo/classificação etária e em OST é intro lenta.
- **Travas de custo** (`data/settings.json`): `max_videos_per_day` (padrão 3)
  e `tts_reserve_chars` (2000). O monitor roda a cada 2 min e a fila de
  notícias é sempre maior que a cota do ElevenLabs — sem essas travas um dia
  de execução queima os créditos do mês inteiro. Uma narração média tem ~370
  caracteres; o plano Starter (30k/mês) dá ~82 vídeos, ou ~2,7 por dia.
- Cada vídeo sai com uma **capa** (`data/covers/item_N.png`): hook grande e
  estático sobre um frame real do gameplay, pra usar como thumbnail no
  upload (a capa é o que aparece na grade do perfil e na busca do TikTok).

É esse o comando configurado no `crontab -l` do sistema (a cada 30 min),
rodando de forma totalmente autônoma sem qualquer sessão de IA/chat aberta.
Os vídeos ficam prontos em `data/videos/item_N.mp4` para o usuário revisar
e subir manualmente no app do TikTok.

### Etapas individuais

```bash
uv run python -m collector.run              # coleta feeds RSS
uv run python -m dedupe.run                 # filtra por relevância
uv run python -m script_gen.run --limit 5   # gera roteiros PT-BR
uv run python -m video_gen.run --limit 5    # gera vídeos (TTS+legendas+render)
uv run python -m publisher.run              # dry-run por padrão
uv run python -m publisher.run --live       # publica de verdade (requer TIKTOK_ACCESS_TOKEN)
```

Feeds monitorados (13, em `feeds.yaml`): blogs **oficiais** PlayStation e
Xbox (dão a notícia antes da imprensa), fontes de **furo/vazamento** (VGC,
Insider Gaming), imprensa generalista (IGN, Eurogamer, GameSpot, Polygon,
PC Gamer, Kotaku), plataformas (Nintendo Life, Push Square) e indústria
(GamesIndustry.biz, com peso menor). O peso de cada fonte no ranking fica em
`dedupe/keyword_filter.py` (`SOURCE_WEIGHTS`); fonte nova sem peso vale 1.0.

A busca usa **GET condicional** (ETag/Last-Modified em `data/feed_cache.json`):
o monitor checa a cada 2 min, e 8 dos 13 feeds respondem 304 quando nada
mudou — sem isso seriam ~400 downloads completos por hora nos servidores dos
portais. O User-Agent precisa ser no formato de leitor de RSS: com a palavra
"bot" no meio, cinco desses portais respondem 403.

Ao avaliar um portal novo, olhe se ele **publica notícia** — agregadores de
SEO (listicle, "códigos grátis", guia) só enchem a fila de ruído. Portais BR
(IGN Brasil, Adrenaline, The Enemy) foram testados e deixados de fora de
propósito: eles traduzem a notícia internacional, então cobrir o que eles
publicam significa chegar depois — o oposto da proposta do canal.

### Monitor contínuo ("tempo real") + cron

`pipeline/watch.py` fica rodando o tempo todo: checa os feeds a cada 2 min
e, quando entra notícia nova, ela passa na hora por ranking → roteiro →
vídeo (modo autônomo: `--require-media`, `--max-age-hours 48`, até 3 por
ciclo). RSS não tem push, então "tempo real" = polling curto. O painel mostra
se o monitor está vivo e há quanto tempo checou (`data/watcher_status.json`).

```bash
scripts/watcher.sh --interval 120 --limit 3 --max-age-hours 48   # roda pra sempre
uv run python -m pipeline.watch --once                            # um ciclo só
```

Crontab instalado (`crontab -l`) — o cron é só o *watchdog* que religa o
monitor se ele morrer (o `flock -n` sai na hora se já estiver rodando):

```cron
*/5 * * * * /caminho/do/projeto/scripts/watcher.sh --interval 120 --limit 3 --max-age-hours 48 >> /caminho/do/projeto/logs/watcher.log 2>&1
@reboot sleep 20 && /caminho/do/projeto/scripts/webapp.sh >> /caminho/do/projeto/logs/webapp.log 2>&1
```

Os scripts em `scripts/` existem porque o cron roda com um `PATH` mínimo:
sem eles `npx` (nvm), `claude` (~/.local/bin) e `yt-dlp` (venv/deno) não são
encontrados. `scripts/pipeline_cron.sh` continua disponível pra rodar o
pipeline em lote (uma rodada) com o mesmo PATH. Logs em `logs/watcher.log`.

### Fila de publicação (upload manual em horário de pico)

A publicação automática depende da Content Posting API aprovada (ver o fim
deste README). Enquanto isso, a ferramenta diz **o que postar e quando**:
cada vídeo pronto recebe um horário nos picos do público BR
(`peak_slots`, padrão 12:15 / 18:45 / 21:15, fuso America/Sao_Paulo),
respeitando `posts_per_day` e `min_gap_minutes`. Notícia **quente e fresca**
(score ≥ `hot_score` e idade ≤ `hot_max_age_hours`) é marcada como
**"postar agora"** — em notícia de games, chegar primeiro vale mais que o
horário nobre. O monitor já agenda tudo sozinho ao fim de cada ciclo; a fila
fica em `/publicar` no painel, com legenda pra copiar e botão de "marcar
como postado". Esses valores ficam em `data/settings.json` (editáveis pelo
painel), junto com a voz do TTS e o nome do canal.

> Automatizar o upload controlando o app do TikTok (GUI/robô de cliques)
> **não** é uma opção aqui: é o que os Termos proíbem explicitamente
> (postagem automatizada fora da API) e o risco é banimento da conta.

## Painel web (webapp/)

Dashboard local em Flask para gerenciar o pipeline sem usar o terminal:
listar/filtrar notícias por status, editar roteiro, disparar geração de
roteiro/vídeo, e o principal — **upload de vídeo de fundo e música
customizados por notícia, escolhendo o trecho exato (início + duração)**.

```bash
scripts/webapp.sh          # ou: uv run python -m webapp.app
# acesse http://localhost:5000 no navegador
```

Funcionalidades:
- Lista de notícias com filtros (relevantes, sem roteiro, sem vídeo, vídeo
  pronto) e busca por título/jogo, com paginação.
- Botões para: buscar notícias novas (collector+dedupe), gerar roteiros em
  lote, gerar vídeos em lote — cada ação roda em background (thread) com
  log de progresso ao vivo, consultável na aba "Tarefas".
- Página de detalhe de cada notícia: editar hook/corpo/CTA/nome do jogo
  manualmente, ou gerar via IA com um clique; gerar/regenerar o vídeo
  individualmente; preview do vídeo final direto no navegador.
- **Upload de vídeo de fundo**: envie um arquivo de vídeo qualquer, escolha
  o segundo de início e a duração do trecho — o sistema recorta/escala pra
  9:16 (30fps constante, evita flicker) e salva como o fundo daquele jogo,
  com prioridade sobre qualquer busca automática via yt-dlp.
- **Upload de música de fundo**: mesma lógica, para a trilha sonora — envie
  um MP3/WAV, escolha o trecho, ele vira a música daquele jogo.
- Botão para remover o fundo/música customizado e voltar à busca automática.

Ferramenta de uso pessoal/local, sem autenticação — não exponha na
internet (é só para `localhost` da própria máquina).

## Estrutura do projeto

```
/collector       -> coleta de RSS/APIs de notícias
/dedupe          -> deduplicação e filtro de relevância
/script_gen      -> geração de roteiro via Claude Code CLI (PT-BR)
/video_gen       -> TTS (ElevenLabs c/ timestamps) + legendas + render (Remotion)
  /remotion      -> projeto Node.js/React com o template do vídeo (9:16)
/publisher       -> integração com TikTok Content Posting API
/pipeline        -> orquestrador end-to-end (todas as etapas)
/shared          -> modelos de dados (NewsItem), acesso ao SQLite, configs
/tests           -> 65 testes, espelhando a estrutura acima, 100% offline
feeds.yaml       -> lista de feeds RSS monitorados
.env.example     -> template de variáveis de ambiente (sem valores reais)
CLAUDE.md        -> especificação detalhada do projeto e convenções
```

## Como cada etapa funciona

**collector**: lê `feeds.yaml`, busca cada feed via `feedparser`, normaliza
em `NewsItem` e salva no SQLite com dedupe automático (hash de título+URL).

**dedupe**: avalia itens ainda não avaliados, marca como relevantes os que
contêm palavras-chave (leak, reveal, delay, launch, exclusive, trailer,
release date, confirmed...). Idempotente.

**script_gen**: para cada item relevante sem roteiro, chama `claude -p` com
um prompt estruturado pedindo hook + corpo + CTA em português, retornando
JSON. Usa a assinatura Claude Pro/Max do usuário via CLI (subprocess),
evitando custo de API por token.

**video_gen**: para cada item com roteiro pronto:
1. Gera narração em áudio via ElevenLabs TTS (`convert_with_timestamps`),
   que já devolve o alinhamento por caractere — daí saem os timestamps por
   palavra das legendas, com o texto exato do roteiro (sem transcrição).
   Termos em inglês são falados com respelling fonético
   (`pronunciations.yaml` global + campo "Pronúncias" gerado por notícia),
   mas a legenda mostra o termo original.
2. (não há mais etapa de transcrição)
3. Se o roteiro identificou um `game_name`, busca um clipe de fundo nesta
   ordem: (a) clipe manual em `video_gen/manual_clips/<slug>.*` fornecido
   por você, (b) clipe já em cache de uma execução anterior, (c) download
   automático de trailer oficial no YouTube via `yt-dlp`. Recorta para 9:16
   e cacheia por jogo em `data/gameplay_cache/`. **Nunca tenta contornar
   verificação de idade/login do YouTube** — se o trailer exigir login, o
   download falha e cai no fundo gradiente, a menos que você tenha colocado
   um clipe manual para aquele jogo (ver `video_gen/manual_clips/README.md`)
4. Monta um spec JSON (roteiro + timings + fundo) e chama
   `npx remotion render`
5. O template Remotion (`video_gen/remotion/src/NewsShort.tsx`) renderiza
   um vídeo vertical 1080x1920 com fundo de gameplay/trailer em loop (ou
   gradiente), hook animado, legendas "karaokê" palavra-a-palavra
   sincronizadas com o áudio, e CTA final

### Clipes manuais (jogos com trailer restrito por idade)

Alguns trailers no YouTube exigem login para confirmar idade. Este projeto
**nunca** tenta contornar essa verificação (sem cookies de sessão, sem
login automatizado, sem nenhum outro método de burlar o gate). Nesses
casos, você pode fornecer o clipe manualmente:

```bash
# descobrir o slug esperado para o nome do jogo
uv run python -c "from video_gen.gameplay import slugify; print(slugify('Nome do Jogo'))"

# colocar o arquivo lá (qualquer formato que o ffmpeg leia)
cp meu_clipe.mp4 video_gen/manual_clips/nome-do-jogo.mp4
```

Na próxima vez que `video_gen.run` processar um item desse jogo, o clipe
manual é detectado automaticamente, recortado/escalado para 9:16 e
cacheado — tem prioridade sobre cache antigo e sobre o download via
YouTube. Detalhes em `video_gen/manual_clips/README.md`.

### ⚠️ Nota sobre baixar clipes do YouTube (yt-dlp)

O `video_gen/gameplay.py` baixa trechos curtos de trailers oficiais do
YouTube via `yt-dlp`. Mesmo sendo material oficial do publisher/estúdio,
baixar conteúdo do YouTube está numa área cinzenta em relação aos Termos de
Serviço da plataforma. Mitigamos o risco usando apenas clipes curtos
(~12s, sem áudio) como plano de fundo secundário — nunca o conteúdo
principal do vídeo. Se isso for uma preocupação, a alternativa mais segura
é substituir por uma biblioteca de capturas/clipes próprios do usuário (ver
`video_gen/gameplay.py` para onde plugar isso).

**publisher**: envia o vídeo pronto para a TikTok Content Posting API.
- Modo `inbox` (padrão): envia como rascunho pra caixa de entrada do TikTok
  do usuário, que revisa e publica manualmente no app — mais seguro
- Modo `direct`: publica direto no perfil (requer escopo `video.publish`
  aprovado pelo TikTok)
- **Dry-run por padrão**: nada é publicado de verdade até passar `--live`
  explicitamente e ter `TIKTOK_ACCESS_TOKEN` configurado

## Testes

```bash
uv run pytest -v
```

65 testes, 100% offline (fixtures locais, mocks de APIs externas, SQLite em
diretório temporário) — nenhuma chamada de rede/custo é feita durante
`pytest`.

## Stack

- **Linguagem:** Python 3.12+
- **Dependências:** uv
- **Banco de dados:** SQLite (dedupe, histórico, estado do pipeline)
- **Coleta:** feedparser (RSS/Atom)
- **Roteiro:** Claude Code CLI (`claude -p`), assinatura Pro/Max
- **TTS:** ElevenLabs (`eleven_multilingual_v2`), voice_settings tunados
  para expressividade (stability baixa, style alto, speed ~1.08)
- **Legendas:** alinhamento por caractere do próprio ElevenLabs (`convert_with_timestamps`) — texto exato do roteiro, sem transcrição
- **Vídeo:** Remotion (React/TypeScript, Node.js), 1080x1920, render via CLI
- **Publicação:** TikTok Content Posting API v2 (`open.tiktokapis.com`)
- **Orquestração:** scripts Python + cron do sistema
- **Testes:** pytest

## Regras e convenções

- Nunca commitar chaves de API, tokens ou credenciais — sempre via `.env`
  (git-ignorado), com `.env.example` documentando as variáveis esperadas
- Cada módulo é testável isoladamente, com baixo acoplamento entre coleta,
  geração e publicação
- Ao gerar vídeo, nunca usar imagens/prints de sites de notícias de
  terceiros — apenas capturas do próprio jogo ou material oficial de
  divulgação, para evitar strike de copyright. O fundo de vídeo agora usa
  clipes de trailers OFICIAIS baixados via yt-dlp (busca "<jogo> official
  trailer"), nunca gameplay de terceiros ou material jornalístico — ver
  nota de risco de ToS abaixo
- Publicação sempre em dry-run por padrão — `--live` é opt-in explícito
- **Antes de rodar o publisher em modo `--live`**, foram validados
  manualmente 5 vídeos gerados ponta a ponta (regra cumprida)

## Publicando de verdade no TikTok

O módulo `publisher` está pronto, mas publicar de verdade exige:
1. App registrado em [developers.tiktok.com](https://developers.tiktok.com)
2. Produto "Content Posting API" solicitado e aprovado (revisão manual da
   TikTok, pode levar dias)
3. Fluxo OAuth2 completado para obter `TIKTOK_ACCESS_TOKEN` com escopo
   `video.upload` (modo inbox) ou `video.publish` (modo direct)
4. Preencher essas credenciais no `.env`

Sem isso, `publisher.run` continua funcionando em dry-run (loga o que
faria, sem chamar a API).

Detalhes completos de especificação e decisões de arquitetura em
[`CLAUDE.md`](./CLAUDE.md).

## Licença

Projeto pessoal — sem licença definida ainda.
