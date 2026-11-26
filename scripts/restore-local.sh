#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
usage() { printf 'Usage: %s <backup.tar.gz> [--yes]\n' "$0"; }

ARCHIVE=""
ASSUME_YES=false
while (($#)); do
  case "$1" in
    --yes) ASSUME_YES=true ;;
    --help|-h) usage; exit 0 ;;
    -*) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *) [[ -z "$ARCHIVE" ]] || { printf 'Only one archive may be supplied.\n' >&2; exit 2; }; ARCHIVE="$1" ;;
  esac
  shift
done
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || { printf 'Backup archive not found.\n' >&2; usage >&2; exit 2; }
for command_name in docker python3 tar sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || { printf 'Required command not found: %s\n' "$command_name" >&2; exit 1; }
done

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mfa-restore.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
if [[ -f "$ARCHIVE.sha256" ]]; then
  (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
else
  printf 'Warning: no adjacent archive checksum; verifying payload checksums only.\n' >&2
fi

python3 - "$ARCHIVE" <<'PY'
import sys,tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1],"r:gz") as archive:
 members=archive.getmembers()
 if not members: raise SystemExit("Backup archive is empty.")
 for item in members:
  path=PurePosixPath(item.name)
  if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0]!="backup":
   raise SystemExit(f"Unsafe archive path: {item.name}")
  if not (item.isfile() or item.isdir()): raise SystemExit(f"Unsupported archive entry: {item.name}")
PY
tar -xzf "$ARCHIVE" -C "$WORK_DIR"
PAYLOAD="$WORK_DIR/backup"
[[ -s "$PAYLOAD/postgres.dump" && -s "$PAYLOAD/manifest.json" && -s "$PAYLOAD/SHA256SUMS" ]] || {
  printf 'Archive is missing required backup files.\n' >&2; exit 1;
}
(cd "$PAYLOAD" && sha256sum -c SHA256SUMS)
FORMAT_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["format_version"])' "$PAYLOAD/manifest.json")"
[[ "$FORMAT_VERSION" == 2 ]] || { printf 'Unsupported backup format: %s (expected 2).\n' "$FORMAT_VERSION" >&2; exit 1; }
DB_NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["postgres_database"])' "$PAYLOAD/manifest.json")"
QDRANT_COLLECTION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["qdrant_collection"])' "$PAYLOAD/manifest.json")"
QDRANT_INCLUDED="$(python3 -c 'import json,sys; print("true" if json.load(open(sys.argv[1]))["qdrant_snapshot_included"] else "false")' "$PAYLOAD/manifest.json")"
SOURCE_QDRANT_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("qdrant_version",""))' "$PAYLOAD/manifest.json")"
[[ "$QDRANT_COLLECTION" =~ ^[A-Za-z0-9_-]+$ ]] || { printf 'Invalid collection in manifest.\n' >&2; exit 1; }
TARGET_DB="$(docker compose exec -T db printenv POSTGRES_DB)"
TARGET_DB_USER="$(docker compose exec -T db printenv POSTGRES_USER)"
[[ "$TARGET_DB" == "$DB_NAME" ]] || { printf 'Target DB %s differs from backup DB %s.\n' "$TARGET_DB" "$DB_NAME" >&2; exit 1; }
docker compose exec -T db pg_restore --list < "$PAYLOAD/postgres.dump" >/dev/null

QDRANT_CONTAINER="$(docker compose ps -q qdrant)"
[[ -n "$QDRANT_CONTAINER" ]] || { printf 'Compose qdrant service is not running.\n' >&2; exit 1; }
QDRANT_NETWORK="$(docker inspect --format '{{range $name, $network := .NetworkSettings.Networks}}{{println $name}}{{end}}' "$QDRANT_CONTAINER" | head -n 1)"
[[ -n "$QDRANT_NETWORK" ]] || { printf 'Could not determine Qdrant Docker network.\n' >&2; exit 1; }
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"
CURL_IMAGE="${QDRANT_CURL_IMAGE:-curlimages/curl:8.12.1}"
[[ "$QDRANT_URL" == http://qdrant:* || "$QDRANT_URL" == https://qdrant:* ]] || { printf 'QDRANT_URL must use the private Compose service name qdrant.\n' >&2; exit 1; }
qdrant_curl() {
  docker run --rm --network "$QDRANT_NETWORK" -v "$WORK_DIR:/backup" \
    -e "QDRANT_API_KEY=$QDRANT_API_KEY" --entrypoint sh "$CURL_IMAGE" -c '
      if [ -n "$QDRANT_API_KEY" ]; then exec curl -H "api-key: $QDRANT_API_KEY" "$@"
      else exec curl "$@"; fi
    ' sh "$@"
}
QDRANT_INFO="$(qdrant_curl -fsS --connect-timeout 10 "$QDRANT_URL/")"
TARGET_QDRANT_VERSION="$(printf '%s' "$QDRANT_INFO" | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')"
if [[ "$QDRANT_INCLUDED" == true ]]; then
  python3 - "$SOURCE_QDRANT_VERSION" "$TARGET_QDRANT_VERSION" <<'PY'
import re,sys
def parts(value):
 match=re.match(r"^v?(\d+)\.(\d+)\.(\d+)",value)
 if not match: raise SystemExit(f"Unrecognized Qdrant version: {value}")
 return tuple(map(int,match.groups()))
source,target=parts(sys.argv[1]),parts(sys.argv[2])
if target[0]!=source[0] or not (target[1]==source[1] and target[2]>=source[2] or target[1]==source[1]+1):
 raise SystemExit(f"Incompatible Qdrant snapshot {sys.argv[1]} for target {sys.argv[2]}.")
PY
  [[ -s "$PAYLOAD/qdrant.snapshot" ]] || { printf 'Qdrant snapshot missing from archive.\n' >&2; exit 1; }
fi

if [[ "$ASSUME_YES" != true ]]; then
  [[ -r /dev/tty ]] || { printf 'Interactive terminal required; pass --yes to confirm destructive restore.\n' >&2; exit 1; }
  printf 'This replaces PostgreSQL database %s and Qdrant collection %s. Type RESTORE: ' "$DB_NAME" "$QDRANT_COLLECTION" >&2
  read -r CONFIRM </dev/tty
  [[ "$CONFIRM" == RESTORE ]] || { printf 'Restore cancelled.\n' >&2; exit 1; }
fi

printf 'Restoring PostgreSQL ...\n'
docker compose exec -T db pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error \
  --username="$TARGET_DB_USER" --dbname="$TARGET_DB" < "$PAYLOAD/postgres.dump"

if [[ "$QDRANT_INCLUDED" == true ]]; then
  SNAPSHOT_SHA256="$(sha256sum "$PAYLOAD/qdrant.snapshot" | cut -d ' ' -f 1)"
  qdrant_curl -fsS -X POST -F "snapshot=@/backup/backup/qdrant.snapshot" \
    "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/upload?priority=snapshot&wait=true&checksum=$SNAPSHOT_SHA256" >/dev/null
  qdrant_curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION" >/dev/null
else
  STATUS="$(qdrant_curl -sS -X DELETE -o /backup/qdrant-delete.json -w '%{http_code}' "$QDRANT_URL/collections/$QDRANT_COLLECTION")"
  [[ "$STATUS" == 200 || "$STATUS" == 404 ]] || { printf 'Could not clear target Qdrant collection (HTTP %s).\n' "$STATUS" >&2; exit 1; }
fi

printf 'Applying Alembic migrations ...\n'
docker compose run --rm migrate
printf '\nRestore commands completed. Verify API health, a known database record and document search before relying on recovery.\n'
