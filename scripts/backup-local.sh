#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for command_name in docker python3 tar sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  }
done

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-mutual_fund_research}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"
CURL_IMAGE="${QDRANT_CURL_IMAGE:-curlimages/curl:8.12.1}"

[[ "$BACKUP_KEEP" =~ ^[0-9]+$ ]] || { printf 'BACKUP_KEEP must be a non-negative integer.\n' >&2; exit 1; }
[[ "$QDRANT_COLLECTION" =~ ^[A-Za-z0-9_-]+$ ]] || { printf 'Invalid QDRANT_COLLECTION.\n' >&2; exit 1; }
[[ "$QDRANT_URL" == http://qdrant:* || "$QDRANT_URL" == https://qdrant:* ]] || {
  printf 'QDRANT_URL must address the private Compose service name qdrant.\n' >&2
  exit 1
}

mkdir -p "$BACKUP_DIR"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mfa-backup.XXXXXX")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUP_DIR/mfa-backup-$STAMP.tar.gz"
ARCHIVE_TMP="$BACKUP_DIR/.mfa-backup-$STAMP.$$.tmp"
SNAPSHOT_NAME=""
cleanup() {
  if [[ -n "$SNAPSHOT_NAME" && -n "${QDRANT_NETWORK:-}" ]]; then
    qdrant_curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAPSHOT_NAME" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR"
  rm -f "$ARCHIVE_TMP"
}
trap cleanup EXIT

QDRANT_CONTAINER="$(docker compose ps -q qdrant)"
[[ -n "$QDRANT_CONTAINER" ]] || { printf 'Compose qdrant service is not running.\n' >&2; exit 1; }
QDRANT_NETWORK="$(docker inspect --format '{{range $name, $network := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$QDRANT_CONTAINER" | head -n 1)"
[[ -n "$QDRANT_NETWORK" ]] || { printf 'Could not determine the Qdrant Compose network.\n' >&2; exit 1; }

qdrant_curl() {
  docker run --rm --network "$QDRANT_NETWORK" -v "$WORK_DIR:/backup" \
    -e "QDRANT_API_KEY=$QDRANT_API_KEY" --entrypoint sh "$CURL_IMAGE" -c '
      if [ -n "$QDRANT_API_KEY" ]; then
        exec curl -H "api-key: $QDRANT_API_KEY" "$@"
      else
        exec curl "$@"
      fi
    ' sh "$@"
}

PAYLOAD="$WORK_DIR/backup"
mkdir -p "$PAYLOAD"
printf 'Checking private Qdrant service over Docker network %s ...\n' "$QDRANT_NETWORK"
QDRANT_INFO="$(qdrant_curl -fsS --connect-timeout 10 "$QDRANT_URL/")"
QDRANT_VERSION="$(printf '%s' "$QDRANT_INFO" | python3 -c '
import json,sys
version=json.load(sys.stdin).get("version")
if not version: raise SystemExit("Qdrant response omitted version.")
print(version)
')"

printf 'Dumping PostgreSQL ...\n'
DB_NAME="$(docker compose exec -T db printenv POSTGRES_DB)"
DB_USER="$(docker compose exec -T db printenv POSTGRES_USER)"
[[ -n "$DB_NAME" && -n "$DB_USER" ]] || { printf 'Missing POSTGRES_DB or POSTGRES_USER.\n' >&2; exit 1; }
docker compose exec -T db pg_dump --format=custom --no-owner --no-acl \
  --username="$DB_USER" --dbname="$DB_NAME" > "$PAYLOAD/postgres.dump"
[[ -s "$PAYLOAD/postgres.dump" ]] || { printf 'PostgreSQL dump is empty.\n' >&2; exit 1; }
docker compose exec -T db pg_restore --list < "$PAYLOAD/postgres.dump" >/dev/null

HTTP_STATUS="$(qdrant_curl -sS --connect-timeout 10 -o /backup/collection.json -w '%{http_code}' "$QDRANT_URL/collections/$QDRANT_COLLECTION")"
QDRANT_INCLUDED=false
if [[ "$HTTP_STATUS" == "200" ]]; then
  SNAPSHOT_RESPONSE="$(qdrant_curl -fsS -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots?wait=true")"
  SNAPSHOT_NAME="$(printf '%s' "$SNAPSHOT_RESPONSE" | python3 -c '
import json,sys
name=json.load(sys.stdin).get("result",{}).get("name")
if not name: raise SystemExit("Qdrant snapshot response omitted result.name.")
print(name)
')"
  [[ "$SNAPSHOT_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || { printf 'Unsafe Qdrant snapshot name.\n' >&2; exit 1; }
  qdrant_curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAPSHOT_NAME" -o /backup/backup/qdrant.snapshot
  [[ -s "$PAYLOAD/qdrant.snapshot" ]] || { printf 'Qdrant snapshot download is empty.\n' >&2; exit 1; }
  QDRANT_INCLUDED=true
  qdrant_curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAPSHOT_NAME" >/dev/null
  SNAPSHOT_NAME=""
elif [[ "$HTTP_STATUS" != "404" ]]; then
  printf 'Qdrant collection check failed with HTTP %s.\n' "$HTTP_STATUS" >&2
  cat "$WORK_DIR/collection.json" >&2
  exit 1
fi

GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
python3 - "$PAYLOAD/manifest.json" "$STAMP" "$DB_NAME" "$DB_USER" "$QDRANT_COLLECTION" "$QDRANT_INCLUDED" "$QDRANT_VERSION" "$GIT_COMMIT" <<'PY'
import json,sys
from datetime import datetime,timezone
path,stamp,db,user,collection,included,version,commit=sys.argv[1:]
data={
 "format_version":2,
 "created_at_utc":datetime.strptime(stamp,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat(),
 "postgres_database":db,"postgres_user":user,"qdrant_collection":collection,
 "qdrant_snapshot_included":included=="true","qdrant_version":version,
 "repository_commit":commit,
}
with open(path,"w",encoding="utf-8") as f: json.dump(data,f,indent=2); f.write("\n")
PY
(
  cd "$PAYLOAD"
  if [[ "$QDRANT_INCLUDED" == true ]]; then sha256sum manifest.json postgres.dump qdrant.snapshot > SHA256SUMS
  else sha256sum manifest.json postgres.dump > SHA256SUMS; fi
)
tar -czf "$ARCHIVE_TMP" -C "$WORK_DIR" backup
tar -tzf "$ARCHIVE_TMP" >/dev/null
mv "$ARCHIVE_TMP" "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"

if (( BACKUP_KEEP > 0 )); then
  python3 - "$BACKUP_DIR" "$BACKUP_KEEP" <<'PY'
from pathlib import Path
import sys
directory,keep=Path(sys.argv[1]),int(sys.argv[2])
archives=sorted(directory.glob("mfa-backup-*.tar.gz"),key=lambda p:p.stat().st_mtime,reverse=True)
for old in archives[keep:]:
 old.unlink(missing_ok=True); old.with_suffix(old.suffix+".sha256").unlink(missing_ok=True)
PY
fi
printf '\nBackup completed.\nArchive: %s\nQdrant snapshot included: %s\n' "$ARCHIVE" "$QDRANT_INCLUDED"
