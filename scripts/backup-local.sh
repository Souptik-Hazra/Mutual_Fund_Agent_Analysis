#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for command_name in docker curl python3 tar sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  }
done

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-mutual_fund_research}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"

[[ "$BACKUP_KEEP" =~ ^[0-9]+$ ]] || {
  printf 'BACKUP_KEEP must be a non-negative integer.\n' >&2
  exit 1
}
[[ "$QDRANT_COLLECTION" =~ ^[A-Za-z0-9_-]+$ ]] || {
  printf 'QDRANT_COLLECTION contains unsupported characters.\n' >&2
  exit 1
}

mkdir -p "$BACKUP_DIR"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mfa-backup.XXXXXX")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUP_DIR/mfa-backup-$STAMP.tar.gz"
ARCHIVE_TMP="$BACKUP_DIR/.mfa-backup-$STAMP.$$.tmp"
SNAPSHOT_NAME=""
QDRANT_HEADERS=()
if [[ -n "$QDRANT_API_KEY" ]]; then
  QDRANT_HEADERS=(-H "api-key: $QDRANT_API_KEY")
fi

cleanup() {
  if [[ -n "$SNAPSHOT_NAME" ]]; then
    curl -fsS -X DELETE "${QDRANT_HEADERS[@]}" \
      "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAPSHOT_NAME" \
      >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR"
  rm -f "$ARCHIVE_TMP"
}
trap cleanup EXIT

PAYLOAD="$WORK_DIR/backup"
mkdir -p "$PAYLOAD"

printf 'Checking Qdrant at %s ...\n' "$QDRANT_URL"
QDRANT_INFO="$(curl -fsS --connect-timeout 10 "${QDRANT_HEADERS[@]}" "$QDRANT_URL/")"
QDRANT_VERSION="$(printf '%s' "$QDRANT_INFO" | python3 -c '
import json, sys
value = json.load(sys.stdin)
version = value.get("version")
if not version:
    raise SystemExit("Qdrant API response did not contain a version.")
print(version)
')"

printf 'Dumping PostgreSQL from the Compose db service ...\n'
DB_NAME="$(docker compose exec -T db sh -lc 'printf "%s" "$POSTGRES_DB"')"
DB_USER="$(docker compose exec -T db sh -lc 'printf "%s" "$POSTGRES_USER"')"
[[ -n "$DB_NAME" && -n "$DB_USER" ]] || {
  printf 'The db service did not expose POSTGRES_DB and POSTGRES_USER.\n' >&2
  exit 1
}
docker compose exec -T db sh -lc \
  'pg_dump --format=custom --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  > "$PAYLOAD/postgres.dump"
[[ -s "$PAYLOAD/postgres.dump" ]] || {
  printf 'PostgreSQL dump is empty.\n' >&2
  exit 1
}

QDRANT_INCLUDED="false"
HTTP_STATUS="$(curl -sS --connect-timeout 10 -o "$WORK_DIR/collection.json" -w '%{http_code}' \
  "${QDRANT_HEADERS[@]}" "$QDRANT_URL/collections/$QDRANT_COLLECTION")"
if [[ "$HTTP_STATUS" == "200" ]]; then
  printf 'Creating Qdrant snapshot for collection %s ...\n' "$QDRANT_COLLECTION"
  SNAPSHOT_RESPONSE="$(curl -fsS -X POST "${QDRANT_HEADERS[@]}" \
    "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots?wait=true")"
  SNAPSHOT_NAME="$(printf '%s' "$SNAPSHOT_RESPONSE" | python3 -c '
import json, sys
value = json.load(sys.stdin)
name = value.get("result", {}).get("name")
if not name:
    raise SystemExit("Qdrant snapshot response did not contain result.name.")
print(name)
')"
  [[ "$SNAPSHOT_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || {
    printf 'Qdrant returned an unsafe snapshot filename.\n' >&2
    exit 1
  }
  curl -fsS "${QDRANT_HEADERS[@]}" \
    "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAPSHOT_NAME" \
    -o "$PAYLOAD/qdrant.snapshot"
  [[ -s "$PAYLOAD/qdrant.snapshot" ]] || {
    printf 'Qdrant snapshot download is empty.\n' >&2
    exit 1
  }
  QDRANT_INCLUDED="true"
  curl -fsS -X DELETE "${QDRANT_HEADERS[@]}" \
    "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAPSHOT_NAME" \
    >/dev/null
  SNAPSHOT_NAME=""
elif [[ "$HTTP_STATUS" == "404" ]]; then
  printf 'Qdrant collection %s does not exist; recording an empty vector-store state.\n' "$QDRANT_COLLECTION"
else
  printf 'Qdrant collection check failed with HTTP %s.\n' "$HTTP_STATUS" >&2
  cat "$WORK_DIR/collection.json" >&2
  exit 1
fi

GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
python3 - "$PAYLOAD/manifest.json" "$STAMP" "$DB_NAME" "$DB_USER" \
  "$QDRANT_COLLECTION" "$QDRANT_INCLUDED" "$QDRANT_VERSION" "$GIT_COMMIT" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, stamp, db_name, db_user, collection, included, version, commit = sys.argv[1:]
manifest = {
    "format_version": 1,
    "created_at_utc": datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    .replace(tzinfo=timezone.utc)
    .isoformat(),
    "postgres_database": db_name,
    "postgres_user": db_user,
    "qdrant_collection": collection,
    "qdrant_snapshot_included": included == "true",
    "qdrant_version": version,
    "repository_commit": commit,
}
with open(path, "w", encoding="utf-8") as output:
    json.dump(manifest, output, indent=2)
    output.write("\n")
PY

(
  cd "$PAYLOAD"
  if [[ "$QDRANT_INCLUDED" == "true" ]]; then
    sha256sum manifest.json postgres.dump qdrant.snapshot > SHA256SUMS
  else
    sha256sum manifest.json postgres.dump > SHA256SUMS
  fi
)

tar -czf "$ARCHIVE_TMP" -C "$WORK_DIR" backup
mv "$ARCHIVE_TMP" "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"

if (( BACKUP_KEEP > 0 )); then
  python3 - "$BACKUP_DIR" "$BACKUP_KEEP" <<'PY'
from pathlib import Path
import sys

directory = Path(sys.argv[1])
keep = int(sys.argv[2])
archives = sorted(
    directory.glob("mfa-backup-*.tar.gz"),
    key=lambda item: item.stat().st_mtime,
    reverse=True,
)
for old in archives[keep:]:
    old.unlink(missing_ok=True)
    old.with_suffix(old.suffix + ".sha256").unlink(missing_ok=True)
PY
fi

printf '\nBackup completed successfully.\n'
printf 'Archive: %s\n' "$ARCHIVE"
printf 'Qdrant snapshot included: %s\n' "$QDRANT_INCLUDED"
printf 'SHA-256: %s\n' "$(cut -d ' ' -f 1 "$ARCHIVE.sha256")"
