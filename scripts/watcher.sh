#!/usr/bin/env bash
# Monitor contínuo (pipeline/watch.py) com o PATH completo do shell.
# Chamado pelo cron a cada 5 min como "watchdog": o flock -n faz a chamada
# sair na hora se o monitor já estiver rodando, e o sobe de novo se ele
# tiver morrido (reboot, crash, WSL reiniciado).
set -u
cd "$(dirname "$0")/.."

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$HOME/.deno/env" ] && . "$HOME/.deno/env"
export PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH"

UV="${UV:-$HOME/.hermes/bin/uv}"
exec flock -n /tmp/tiktok-gamenews-watcher.lock "$UV" run python -m pipeline.watch "$@"
