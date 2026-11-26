#!/usr/bin/env bash
set -e
sudo service docker start
docker compose up -d db qdrant
echo
echo "PostgreSQL and Qdrant are running. This terminal will remain open."
exec bash -i
