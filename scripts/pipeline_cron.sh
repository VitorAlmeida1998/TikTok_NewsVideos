#!/usr/bin/env bash
# Roda o pipeline autônomo a partir do cron com o MESMO PATH do shell
# interativo (nvm -> npx/remotion, deno -> yt-dlp, .venv -> yt-dlp/ffmpeg).
# O cron vem com PATH mínimo, e sem isso o render falha com
# "Permission denied: 'npx'" / "No such file: 'yt-dlp'".
#
# flock -n: se a rodada anterior ainda estiver renderizando, esta é pulada
# em vez de rodar duas em paralelo brigando pelo banco e pela CPU.
set -u
cd "$(dirname "$0")/.."

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$HOME/.deno/env" ] && . "$HOME/.deno/env"
export PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH"

UV="${UV:-$HOME/.hermes/bin/uv}"
exec flock -n /tmp/tiktok-gamenews-pipeline.lock "$UV" run python -m pipeline.run "$@"
