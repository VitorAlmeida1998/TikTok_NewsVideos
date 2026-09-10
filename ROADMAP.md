# Roadmap, análise de SEO/viralização e opinião de crescimento

Data: 2026-09-09. Base: 19 vídeos gerados, 477 notícias coletadas (136
relevantes), 5 feeds. Escrito no papel de especialista de crescimento — com
opinião sincera, não só elogio.

## 1. Diagnóstico honesto do produto e da página

**O que está forte**
- Velocidade real: com o monitor contínuo, uma notícia vira vídeo pronto em
  ~5 min depois de sair no feed. Isso é a única vantagem defensável do
  canal — ninguém em PT-BR cobre tão rápido. Tudo no roadmap deve proteger
  isso.
- Formato consistente (hook no topo, legenda karaokê, selo, CTA, marca) e
  produção 100% automática com fundo + música obrigatórios. É um padrão
  reconhecível, que é o que faz alguém seguir um canal de notícias.
- Ranking + fila: a máquina escolhe sozinha o que fazer primeiro.

**O que está fraco (e importa mais que qualquer animação)**
1. **Nome do canal.** "TikTok GameNews" usa a marca TikTok — isso fere as
   diretrizes de marca da plataforma, não é registrável, não funciona no
   YouTube Shorts/Reels e não tem personalidade. Um canal de notícias vive
   de marca. Trocar por um nome próprio curto (2–3 sílabas, que caiba na
   marca d'água e num "@") é a decisão mais barata e de maior impacto que
   existe hoje.
2. **Voz.** A voz atual (Adam, voz inglesa do ElevenLabs) fala português
   com sotaque. O público BR percebe em 1 segundo e isso derruba retenção e
   confiança em "notícia". Testar 2–3 vozes nativas PT-BR da biblioteca do
   ElevenLabs (busca "Brazilian Portuguese") é prioridade 1 de qualidade.
3. **Sem loop de feedback.** A ferramenta não sabe qual vídeo performou.
   Todo peso do ranking é palpite meu. Sem números de views/retenção/shares
   por vídeo, o ranking nunca melhora.
4. **Formato "notícia lida por TTS" é lotado.** Há dezenas de canais BR
   iguais. O que diferencia: (a) chegar primeiro — já temos, (b) uma frase de
   opinião/posicionamento por vídeo ("na minha opinião isso é golpe da
   Rockstar") — comentário nasce de opinião, não de fato, (c) séries com
   nome ("Vazou hoje", "Resumo do Direct em 30s").
5. **Duplicatas de história.** Já saíram dois vídeos contraditórios do
   mesmo assunto (#282 "Forza atrasou no PS5" e #3972 "Forza NÃO atrasou").
   Fontes diferentes = a mesma história vira 2–3 vídeos. Isso queima
   credibilidade e créditos de TTS.
6. **Risco de copyright da música.** OST oficial dispara Content ID no
   TikTok (áudio silenciado ou vídeo derrubado). O ganho de viralização da
   OST é pequeno; o risco é o vídeo inteiro. Sugestão: manter OST só pra
   jogos onde a música É a notícia, e usar áudio da biblioteca comercial do
   TikTok/trilha própria no resto.

## 2. Análise de SEO dos vídeos gerados

Dados dos 19 vídeos: duração 18–35 s (mediana 27,5 s — dentro da faixa boa
de 21–34 s pra notícia); hook médio de 10,7 palavras; 13 CTAs de comentário,
2 de seguir, 0 de "manda pro amigo"; 9 de 19 com descrição; hashtags mais
usadas: #gaming (10), #fyp (9), #gamenews (8), #gamertok (5).

**Problemas encontrados**
- **Zero hashtags em português.** O público é BR e busca "#games",
  "#jogos", "#noticiasdegames", "#vazou". Tudo estava em inglês genérico.
  *(Corrigido no prompt: obriga ≥1 hashtag PT e a palavra de busca na
  primeira frase da legenda.)*
- **Hashtag quebrada**: "#leon kennedy" (espaço). *(Regra adicionada.)*
- **Hook repetitivo**: 6 de 19 começam com "GENTE,". Funciona uma vez;
  repetido vira tique e o algoritmo/público lê como template.
- **CTA sem gatilho de envio.** Nenhum vídeo pedia "manda pra aquele amigo
  que…". Envio por DM é o sinal que mais tira o vídeo da bolha. *(Modo 3 de
  CTA adicionado ao prompt.)*
- **Legenda descritiva longa demais** em alguns (fica cortada no feed —
  primeiras ~6 palavras precisam carregar o jogo + o fato).
- **Sem texto de capa**: o TikTok usa a capa na aba do perfil e na busca;
  hoje a capa é o frame 0 (hook ainda animando). Precisa de um frame de
  capa com título grande e estático.

**Chance de viralizar / ser enviado pra terceiro — como pontuar**
Na prática, vídeo de notícia de games viraliza por 4 gatilhos, nesta ordem:
1. **Afeta uma decisão de alguém** (preço, data, de graça, atraso,
   cancelamento) → gera envio por DM ("olha isso"). Peso alto.
2. **Drama/polêmica/vazamento** (leak, spoiler, processo, banimento) →
   gera comentário e stitch.
3. **Tamanho da franquia** (GTA, Nintendo, Zelda, Pokémon, CoD) →
   multiplica tudo acima.
4. **Frescor**: cada hora depois da fonte original corta o alcance
   (o TikTok já vai estar cheio do assunto).

O `relevance_score` já cobre 2, 3 e parte de 1; hoje adicionei os gatilhos
de decisão (free/price/cancelled/remake/spoiler/banned/lawsuit/record) aos
pesos. O que falta é o item 4 como decaimento por hora e, principalmente,
calibrar os pesos com dados reais (fase 2).

Estimativa honesta com o formato atual: a maioria dos vídeos vai ficar na
faixa de 300–3 mil views (nível "canal novo de notícia com TTS"); os com
gatilho 1+3 (ex: preço/data de GTA 6, Switch 2, Zelda) têm chance real de
10–100 mil se saírem em menos de 1 h da fonte e com voz nativa. Sem trocar
nome e voz, o teto é baixo independente do resto.

## 3. Roadmap

### Feito hoje (2026-09-09)
- Modo autônomo: monitor contínuo (2 min), ranking por relevância, fundo +
  música obrigatórios com fila "aguardando mídia", cron só como watchdog.
- Template Remotion profissional (fonte, Ken Burns, legendas em blocos,
  selo, CTA, barra de progresso, nudge "segue o perfil").
- Legendas com o texto exato do roteiro (alinhamento do ElevenLabs) e
  respelling de pronúncia pra termos em inglês.
- Clipes/OST do YouTube cortados a partir do meio do vídeo.
- Prompt: CTA "marca um amigo", hashtags PT-BR, regra de hashtag.

### Fase 1 — feito em 2026-09-09 (segunda leva)
- [x] **Frame de capa** por vídeo (`NewsCover` + `video_gen/cover.py`):
      hook estático grande sobre um frame real do gameplay (25% do clipe),
      selo e nome do jogo — legível como miniatura de 200 px.
- [x] **Anti-duplicata de história** (`dedupe/story_group.py`): notícias
      parecidas em 36 h viram um `story_group`; só a primeira vira vídeo.
      As outras continuam acessíveis no painel, com aviso de qual já virou.
- [x] **Decaimento por frescor** no ranking (`EFFECTIVE_SCORE_SQL`): a fila
      ordena por relevância × frescor, então notícia parada perde a vez.
- [x] **Variar aberturas**: os 10 hooks mais recentes vão no prompt com
      instrução de não repetir a primeira palavra nem a estrutura.
- [x] **Checklist de SEO** por item no painel (`webapp/seo.py`).
- [x] **Comparador de vozes** no painel (`/vozes`) — a escolha fica em
      `data/settings.json` e vale no próximo vídeo.
- [x] **Fila de publicação** (`/publicar`) com horário de pico BR, legenda
      pronta pra copiar e "marcar como postado"; o monitor agenda sozinho.
- [x] **Travas de custo**: teto de vídeos por dia + reserva de caracteres do
      ElevenLabs (ver a seção de custo abaixo).
- [x] **Fila com curadoria automática**: vídeo com mais de 48h entra como
      "passou o ponto" (não ocupa horário nobre) e, quando dois vídeos
      cobrem a mesma história, só o melhor colocado ganha vaga — o outro
      aparece como "história repetida" em vez de ir pro ar.

### Fase 1 — o que ainda depende de você
- [ ] **Trocar o nome/marca do canal** (decisão sua): mexer em
      `channel_handle`/`channel_initials` em `data/settings.json`.
- [ ] **Escolher uma voz nativa PT-BR** em `/vozes`: cole o voice_id de uma
      voz brasileira da biblioteca do ElevenLabs, gere a amostra e ouça. É a
      maior melhoria de retenção disponível, e eu não consigo julgar por você
      (não escuto o áudio).
- [ ] Habilitar a permissão `voices_read` na API key do ElevenLabs se quiser
      que o painel liste as vozes automaticamente em vez de colar o id.

### Fase 2 — 1 mês (loop de feedback + retenção)
- [ ] Registrar métricas por vídeo (views, retenção média, shares,
      comentários, follows) — manual no painel primeiro; via TikTok API
      depois — e recalibrar `KEYWORD_WEIGHTS`/`HYPE_TERMS` com os dados.
- [ ] "Beat de opinião": uma frase de posicionamento no BODY (configurável
      por tipo de notícia) pra puxar comentário.
- [ ] Séries com identidade visual (selo + cor): "Vazou hoje", "Resumo do
      Direct", "Preço e data".
- [ ] Fundo com 2–3 clipes por vídeo (corte a cada ~8 s) em vez de um clipe
      só em loop — retenção visual.
- [ ] Fallback de mídia que não trava a fila: screenshots oficiais (Steam
      Store API / press kit) quando o trailer for restrito.
- [ ] Sting sonoro de marca (0,4 s) na entrada + música da biblioteca
      comercial do TikTok como padrão; OST só opt-in por jogo.

### Fase 3 — 2–3 meses (distribuição)
- [ ] Publicação automática (Content Posting API — código pronto, falta
      aprovação do app), com horário sugerido por faixa de pico BR (12–13 h,
      18–22 h) e limite de 3–4 posts/dia.
- [ ] Multi-plataforma: YouTube Shorts e Reels com o mesmo mp4 + legenda
      adaptada (Shorts indexa título; Reels prioriza áudio original).
- [ ] Fontes além de RSS: Steam News API, blogs oficiais (PlayStation,
      Xbox Wire, Nintendo), X/Twitter dos publishers — são mais rápidos que
      IGN/Eurogamer, e velocidade é o produto.
- [ ] Painel de performance: ranking previsto × real por vídeo.

## 3.5. O custo é o teto real da operação (descoberto em 2026-09-09)

O plano ElevenLabs é **Starter: 30.074 caracteres/mês** e 9.476 já foram
usados. Uma narração média tem **369 caracteres**, então:

| vídeos/dia | consumo/mês | cabe no Starter (30k)? |
|---|---|---|
| 2 | 22,1k | sim |
| 3 | 33,2k | **não** |
| 4 | 44,3k | não |

Ou seja: o plano atual dá **~82 vídeos/mês (2,7 por dia)**. Isso muda o
desenho da operação — não adianta a máquina achar 50 notícias relevantes por
dia se só 2 ou 3 podem virar áudio. Duas consequências já implementadas:

- `max_videos_per_day` (padrão 3) e uma reserva de caracteres
  (`tts_reserve_chars`) que para a geração automática antes de zerar a cota.
  **Sem isso o monitor rodando a cada 2 min queimaria o mês inteiro numa
  tarde** — foi o bug mais perigoso desta rodada.
- Um vídeo por história (anti-duplicata) deixou de gastar cota com cobertura
  repetida do mesmo fato.

Decisão que vale a pena pesar: subir pro plano Creator (100k caracteres,
~270 vídeos/mês) só faz sentido **depois** que os números provarem que vale
postar 3–4×/dia. Antes disso, 2 vídeos/dia bem escolhidos > 5 medianos.

## 4. O que eu faria amanhã, na ordem
1. **Nome do canal** (10 min, maior impacto por minuto gasto).
2. **Voz PT-BR** em `/vozes` — ouvir 3 candidatas e fixar uma.
3. **Postar 2/dia por uma semana** usando a fila de `/publicar`, anotando
   views/shares. Sem esse dado, todo o resto é palpite meu.
4. Só então: mais animação, mais fontes, mais volume. A produção já está
   acima da média do nicho — o gargalo agora é identidade, voz e dados.
