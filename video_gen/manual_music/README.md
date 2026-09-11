# Faixas manuais de música de fundo (OST/tema do jogo)

Coloque aqui arquivos de áudio que você mesmo forneceu (comprados,
licenciados, ou baixados fora deste sistema) para usar como música de
fundo dos vídeos do pipeline, quando o download automático via YouTube
(`yt-dlp`) falhar — por exemplo, faixas com restrição de idade que exigem
login.

## Como nomear o arquivo

O sistema procura pelo nome do jogo "slugificado": minúsculo, espaços e
caracteres especiais viram hífen (mesma função usada para os clipes de
gameplay). Exemplos:

| Nome do jogo (game_name gerado pelo script_gen) | Nome de arquivo esperado |
|---|---|
| `Squadron 42` | `squadron-42.mp3` |
| `The Blood of Dawnwalker` | `the-blood-of-dawnwalker.mp3` |
| `Onimusha: Way of the Sword` | `onimusha-way-of-the-sword.mp3` |

Para conferir o slug exato de um jogo, rode:

```bash
uv run python -c "from video_gen.gameplay import slugify; print(slugify('Nome do Jogo'))"
```

## Formatos aceitos

Qualquer formato que o ffmpeg lê: `.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`.

## O que acontece com o arquivo

Na primeira vez que for usada, a faixa é automaticamente recortada pros
primeiros ~60 segundos, convertida pra mp3 e salva em
`data/music_cache/<slug>.mp3` — não precisa editar o áudio manualmente
antes de colocar aqui.

## Prioridade

Faixas manuais têm prioridade sobre o cache automático e sobre o download
via YouTube — se você colocar um arquivo aqui para um jogo que já tem
faixa em `data/music_cache/`, apague o cache antigo
(`data/music_cache/<slug>.mp3`) para forçar o reprocessamento com a nova
faixa manual.

## ⚠️ Aviso sobre direitos autorais

Trilhas sonoras oficiais de jogos são material protegido por copyright do
publisher/estúdio/compositor. Usar essa música nos vídeos publicados no
TikTok é uma decisão explícita do usuário, que assume o risco de
Content ID / silenciamento de áudio / remoção do vídeo pela plataforma.

Arquivos desta pasta não são versionados no git (adicionado ao
`.gitignore`).
