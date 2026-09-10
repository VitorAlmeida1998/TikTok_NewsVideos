#!/usr/bin/env bash
# Sobe o painel web (http://localhost:5000) com o PATH completo — usado pelo
# @reboot do cron e também serve pra subir na mão: scripts/webapp.sh
set -u
cd "$(dirname "$0")/.."

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$HOME/.deno/env" ] && . "$HOME/.deno/env"
export PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH"

UV="${UV:-$HOME/.hermes/bin/uv}"
exec "$UV" run python -m webapp.app
