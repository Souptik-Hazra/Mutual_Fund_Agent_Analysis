#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  printf 'Usage: %s <backup.tar.gz> [--yes]\n' "$0"
  printf 'Restoring replaces PostgreSQL objects and the configured Qdrant collection.\n'
}

ARCHIVE=""
ASSUME_YES="false"
while (($#)); do
  case "$1" in
    --yes)
      ASSUME_YES="true"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$ARCHIVE" ]]; then
        printf 'Only one backup archive may be supplied.\n' >&2
        usage >&2
        exit 2
      fi
      ARCHIVE="$1"
      ;;
  esac
  shift
done

[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || {
  printf 'Backup archive not found.\n' >&2
  usage >&2
  exit 2
}

for command_name in docker curl python3 tar sha256sum; do
  command -v "$command_name" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$command_name" >&2
    exit 1
  }
done

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mfa-restore.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
if [[ -f "$ARCHIVE.sha256" ]]; then
  (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
else
  printf 'Warning: no adjacent archive checksum file; verifying the payload checksums only.\n' >&2
fi

python3 - "$ARCHIVE" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], "r:gz") as archive:
    members = archive.getmembers()
    if not members:
        raise SystemExit("Backup archive is empty.")
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "backup":
            raise SystemExit(f"Unsafe path in backup archive: {member.name}")
        if member.issym() or member.islnk():
            raise SystemExit(f"Links are not allowed in backup archives: {member.name}")
PY

tar -xzf "$ARCHIVE" -C "$WORK_DIR"
PAYLOAD="$WORK_DIR/backup"
[[ -s "$PAYLOAD/postgres.dump" && -s "$PAYLOAD/manifest.json" && -s "$PAYLOAD/SHA256SUMS" ]] || {
  printf 'Backup archive is missing required PostgreSQL or manifest files.\n' >&2
  exit 1
}
(
  cd "$PAYLOAD"
  sha256sum -c SHA256SUMS
)

FORMAT_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("format_version", ""))' "$PAYLOAD/manifest.json")"
[[ "$FORMAT_VERSION" == "1" ]] || {
  printf 'Unsupported backup format version: %s\n' "$FORMAT_VERSION" >&2
  exit 1
}
DB_NAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["postgres_database"])' "$PAYLOAD/manifest.json")"
QDRANT_COLLECTION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["qdrant_collection"])' "$PAYLOAD/manifest.json")"
QDRANT_INCLUDED="$(python3 -c 'import json,sys; print("true" if json.load(open(sys.argv[1], encoding="utf-8"))["qdrant_snapshot_included"] else "false")' "$PAYLOAD/manifest.json")"
SOURCE_QDRANT_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("qdrant_version", ""))' "$PAYLOAD/manifest.json")"
[[ "$QDRANT_COLLECTION" =~ ^[A-Za-z0-9_-]+$ ]] || {
  printf 'The manifest contains an invalid Qdrant collection name.\n' >&2
  exit 1
}

TARGET_DB_NAME="$(docker compose exec -T db printenv POSTGRES_DB)"
[[ "$TARGET_DB_NAME" == "$DB_NAME" ]] || {
  printf 'Backup database is %s, but the Compose db target is %s. Refusing to restore to a different database.\n' \
    "$DB_NAME" "$TARGET_DB_NAME" >&2
  exit 1
}
docker compose exec -T db pg_restore --list < "$PAYLOAD/postgres.dump" >/dev/null

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_API_KEY="${QDRANT_API_KEY:-}"
QDRANT_HEADERS=()
if [[ -n "$QDRANT_API_KEY" ]]; then
  QDRANT_HEADERS=(-H "api-key: $QDRANT_API_KEY")
fi
QDRANT_INFO="$(curl -fsS --connect-timeout 10 "${QDRANT_HEADERS[@]}" "$QDRANT_URL/")"
TARGET_QDRANT_VERSION="$(printf '%s' "$QDRANT_INFO" | python3 -c '
import json, sys
value = json.load(sys.stdin)
version = value.get("version")
if not version:
    raise SystemExit("Qdrant API response did not contain a version.")
print(version)
')"

if [[ "$QDRANT_INCLUDED" == "true" ]]; then
  python3 - "$SOURCE_QDRANT_VERSION" "$TARGET_QDRANT_VERSION" <<'PY'
import re
import sys

def version_parts(value: str) -> tuple[int, int]:
    match = re.match(r"^v?(\d+)\.(\d+)\.", value)
    if not match:
        raise SystemExit(f"Unrecognized Qdrant version: {value}")
    return int(match.group(1)), int(match.group(2))

source = version_parts(sys.argv[1])
target = version_parts(sys.argv[2])
if target[0] != source[0] or target[1] not in (source[1], source[1] + 1):
    raise SystemExit(
        f"Incompatible Qdrant snapshot version {sys.argv[1]} for target {sys.argv[2]}. "
        "Use the same minor version or the next minor version."
    )
PY
  [[ -s "$PAYLOAD/qdrant.snapshot" ]] || {
    printf 'Manifest expects a Qdrant snapshot, but the snapshot file is missing.\n' >&2
    exit 1
  }
fi

if [[ "$ASSUME_YES" != "true" ]]; then
  if [[ ! -r /dev/tty ]]; then
    printf 'Interactive terminal required. Review the backup, then rerun with --yes to confirm the destructive restore.\n' >&2
    exit 1
  fi
  printf '\nWARNING: This operation will replace data in PostgreSQL database %s and Qdrant collection %s.\n' \
    "$DB_NAME" "$QDRANT_COLLECTION" >&2
  printf 'Type RESTORE to continue: ' >&2
  read -r CONFIRM </dev/tty
  [[ "$CONFIRM" == "RESTORE" ]] || {
    printf 'Restore cancelled.\n' >&2
    exit 1
  }
fi

printf 'Restoring PostgreSQL database %s ...\n' "$DB_NAME"
TARGET_DB_USER="$(docker compose exec -T db printenv POSTGRES_USER)"
docker compose exec -T db pg_restore --clean --if-exists --no-owner --no-privileges \
  --exit-on-error --username="$TARGET_DB_USER" --dbname="$TARGET_DB_NAME" \
  < "$PAYLOAD/postgres.dump"

if [[ "$QDRANT_INCLUDED" == "true" ]]; then
  printf 'Restoring Qdrant collection %s ...\n' "$QDRANT_COLLECTION"
  curl -fsS -X POST "${QDRANT_HEADERS[@]}" \
    -F "snapshot=@$PAYLOAD/qdrant.snapshot" \
    "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/upload?priority=snapshot&wait=true" \
    >/dev/null
  curl -fsS "${QDRANT_HEADERS[@]}" "$QDRANT_URL/collections/$QDRANT_COLLECTION" >/dev/null
else
  printf 'The backup contains no Qdrant collection; removing any current %s collection.\n' "$QDRANT_COLLECTION"
  HTTP_STATUS="$(curl -sS -X DELETE --connect-timeout 10 -o "$WORK_DIR/qdrant-delete.json" \
    -w '%{http_code}' "${QDRANT_HEADERS[@]}" "$QDRANT_URL/collections/$QDRANT_COLLECTION")"
  [[ "$HTTP_STATUS" == "200" || "$HTTP_STATUS" == "404" ]] || {
    printf 'Qdrant collection cleanup failed with HTTP %s.\n' "$HTTP_STATUS" >&2
    cat "$WORK_DIR/qdrant-delete.json" >&2
    exit 1
  }
fi

printf 'Applying any migrations introduced after this backup ...\n'
docker compose run --rm migrate

printf '\nRestore completed. Verify the API, scheme catalogue, and document search before continuing work.\n'
