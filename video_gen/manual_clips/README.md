# Clipes manuais de gameplay/trailer

Coloque aqui vídeos que você mesmo gravou ou baixou (fora deste sistema)
para usar como fundo dos vídeos do pipeline, quando o download automático
via YouTube (`yt-dlp`) falhar — por exemplo, trailers com restrição de
idade que exigem login.

## Como nomear o arquivo

O sistema procura pelo nome do jogo "slugificado": minúsculo, espaços e
caracteres especiais viram hífen. Exemplos:

| Nome do jogo (game_name gerado pelo script_gen) | Nome de arquivo esperado |
|---|---|
| `Squadron 42` | `squadron-42.mp4` |
| `The Blood of Dawnwalker` | `the-blood-of-dawnwalker.mp4` |
| `Onimusha: Way of the Sword` | `onimusha-way-of-the-sword.mp4` |

Para conferir o slug exato de um jogo, rode:

```bash
uv run python -c "from video_gen.gameplay import slugify; print(slugify('Nome do Jogo'))"
```

Ou veja a coluna `game_name` no banco (`data/news.db`, tabela `news_items`)
para o item específico que falhou o download automático — o log do
`video_gen.run` também avisa o slug esperado quando o yt-dlp falha.

## Formatos aceitos

Qualquer formato que o ffmpeg lê: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`.

## O que acontece com o arquivo

Na primeira vez que for usado, o clipe é automaticamente recortado pros
primeiros ~12 segundos, cortado/escalado pra formato vertical 9:16
(1080x1920) e salvo em `data/gameplay_cache/<slug>.mp4` — não precisa
editar o vídeo manualmente antes de colocar aqui, qualquer resolução/
proporção funciona (o crop é central).

## Prioridade

Clipes manuais têm prioridade sobre o cache automático e sobre o download
via YouTube — se você colocar um arquivo aqui para um jogo que já tem clipe
em `data/gameplay_cache/`, apague o cache antigo (`data/gameplay_cache/<slug>.mp4`)
para forçar o reprocessamento com o novo clipe manual.

Arquivos desta pasta não são versionados no git (`.gitignore`).
