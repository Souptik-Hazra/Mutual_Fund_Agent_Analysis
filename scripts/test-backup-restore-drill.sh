#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Isolate every container and volume from the user's normal local application.
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-mfa-restore-drill-$(date +%s)-$$}"
export QDRANT_COLLECTION="mfa_restore_drill"
export QDRANT_URL="http://qdrant:6333"
export QDRANT_CURL_IMAGE="${QDRANT_CURL_IMAGE:-curlimages/curl:8.12.1}"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mfa-restore-drill.XXXXXX")"
export BACKUP_DIR
cleanup() {
  docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

for command_name in docker; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  }
done
docker compose version >/dev/null

printf 'Starting isolated PostgreSQL and Qdrant services (%s) ...\n' "$COMPOSE_PROJECT_NAME"
docker compose up -d db qdrant
docker compose run --rm migrate

DB_CONTAINER="$(docker compose ps -q db)"
QDRANT_CONTAINER="$(docker compose ps -q qdrant)"
[[ -n "$DB_CONTAINER" && -n "$QDRANT_CONTAINER" ]] || {
  printf 'Isolated database/vector services did not start.\n' >&2
  exit 1
}
NETWORK="$(docker inspect --format '{{range $name, $network := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$QDRANT_CONTAINER" | head -n 1)"
[[ -n "$NETWORK" ]] || { printf 'Could not determine isolated Docker network.\n' >&2; exit 1; }

qdrant_curl() {
  docker run --rm --network "$NETWORK" "$QDRANT_CURL_IMAGE" "$@"
}
for attempt in $(seq 1 30); do
  if qdrant_curl -fsS "$QDRANT_URL/" >/dev/null 2>&1; then break; fi
  if [[ "$attempt" == 30 ]]; then
    printf 'Qdrant did not become ready.\n' >&2
    exit 1
  fi
  sleep 1
done

printf 'Creating disposable database and vector fixtures ...\n'
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U mfa -d mutual_fund_agent \
  -c "INSERT INTO mutual_fund_schemes (scheme_code, scheme_name, source) VALUES (99999999, 'Restore Drill Baseline', 'restore_drill') ON CONFLICT (scheme_code) DO UPDATE SET scheme_name = EXCLUDED.scheme_name;"

qdrant_curl -fsS -X PUT "$QDRANT_URL/collections/$QDRANT_COLLECTION" \
  -H 'Content-Type: application/json' \
  -d '{"vectors":{"size":2,"distance":"Cosine"}}' >/dev/null
qdrant_curl -fsS -X PUT "$QDRANT_URL/collections/$QDRANT_COLLECTION/points?wait=true" \
  -H 'Content-Type: application/json' \
  -d '{"points":[{"id":"00000000-0000-4000-8000-000000000001","vector":[0.25,0.75],"payload":{"metadata":{"document_id":99999999,"chunk_index":0}}}]}' >/dev/null

printf 'Creating PostgreSQL and Qdrant backup ...\n'
BACKUP_KEEP=0 ./scripts/backup-local.sh
ARCHIVE="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'mfa-backup-*.tar.gz' -print -quit)"
[[ -n "$ARCHIVE" && -s "$ARCHIVE" ]] || { printf 'Backup archive was not created.\n' >&2; exit 1; }

printf 'Mutating both services to prove restoration ...\n'
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U mfa -d mutual_fund_agent \
  -c "UPDATE mutual_fund_schemes SET scheme_name = 'Restore Drill Mutated' WHERE scheme_code = 99999999;"
qdrant_curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION/points/delete?wait=true" \
  -H 'Content-Type: application/json' \
  -d '{"points":["00000000-0000-4000-8000-000000000001"]}' >/dev/null

printf 'Restoring the archive into the isolated services ...\n'
./scripts/restore-local.sh "$ARCHIVE" --yes

RESTORED_NAME="$(docker compose exec -T db psql -At -U mfa -d mutual_fund_agent \
  -c "SELECT scheme_name FROM mutual_fund_schemes WHERE scheme_code = 99999999;")"
[[ "$RESTORED_NAME" == "Restore Drill Baseline" ]] || {
  printf 'PostgreSQL restore mismatch: %s\n' "$RESTORED_NAME" >&2
  exit 1
}
RESTORED_POINTS="$(qdrant_curl -fsS -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/points/scroll" \
  -H 'Content-Type: application/json' -d '{"with_payload":true,"limit":10}')"
python3 - "$RESTORED_POINTS" <<'PY'
import json,sys
payload=json.loads(sys.argv[1])
points=payload.get("result",{}).get("points",[])
if len(points)!=1 or points[0].get("id")!="00000000-0000-4000-8000-000000000001":
    raise SystemExit("Qdrant snapshot restore did not recover the expected document point.")
PY
printf 'Disposable PostgreSQL + Qdrant backup/restore drill passed.\n'
