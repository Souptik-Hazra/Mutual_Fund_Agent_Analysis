#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

sudo service docker start
docker compose up -d db qdrant

echo
echo "PostgreSQL and Qdrant are running. This terminal will remain open."
exec bash -i
