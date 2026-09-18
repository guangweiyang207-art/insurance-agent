#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  cp "$DEPLOY_DIR/.env.example" "$ENV_FILE"
  echo "Created deploy/.env from deploy/.env.example. Review secrets before production use."
fi

docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/docker-compose.yml" up -d --build
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/docker-compose.yml" ps
