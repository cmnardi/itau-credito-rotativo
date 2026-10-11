#!/bin/sh
set -e

# Garante que o diretório do banco (volume) é gravável pelo appuser.
if [ "$CREDITO_PERSISTENCIA" = "sqlite" ]; then
    mkdir -p "$(dirname "$CREDITO_DB_PATH")"
    chown -R appuser:appuser "$(dirname "$CREDITO_DB_PATH")" 2>/dev/null || true
fi

# Cai para o usuário não privilegiado e sobe a API.
exec su appuser -c "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
