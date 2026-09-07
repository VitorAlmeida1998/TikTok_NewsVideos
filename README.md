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
| `video_gen` | ✅ pronto | TTS (ElevenLabs) + legendas (faster-whisper) + render (Remotion) |
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

### Etapas individuais

```bash
uv run python -m collector.run              # coleta feeds RSS
uv run python -m dedupe.run                 # filtra por relevância
uv run python -m script_gen.run --limit 5   # gera roteiros PT-BR
uv run python -m video_gen.run --limit 5    # gera vídeos (TTS+legendas+render)
uv run python -m publisher.run              # dry-run por padrão
uv run python -m publisher.run --live       # publica de verdade (requer TIKTOK_ACCESS_TOKEN)
```

Feeds padrão: IGN, Kotaku, GamesIndustry.biz, PC Gamer, Eurogamer. Edite
`feeds.yaml` para adicionar/remover fontes.

### Rodando via cron

Já instalado no crontab do sistema (a cada 30 min, dry-run):

```cron
*/30 * * * * cd /caminho/do/projeto && uv run python -m pipeline.run --limit 5 >> logs/pipeline.log 2>&1
```

Verifique/edite com `crontab -e`. Logs em `logs/pipeline.log`.

## Estrutura do projeto

```
/collector       -> coleta de RSS/APIs de notícias
/dedupe          -> deduplicação e filtro de relevância
/script_gen      -> geração de roteiro via Claude Code CLI (PT-BR)
/video_gen       -> TTS (ElevenLabs) + legendas (whisper) + render (Remotion)
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
1. Gera narração em áudio via ElevenLabs TTS
2. Transcreve o áudio com `faster-whisper` (local, offline) para obter
   timestamps por palavra
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
- **Legendas:** faster-whisper (local, CPU, modelo `base`)
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
