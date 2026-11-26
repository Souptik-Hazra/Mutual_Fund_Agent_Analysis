# Local backup and recovery

This personal, single-node Docker Compose workflow protects the PostgreSQL application
database and the configured Qdrant collection. It does not copy credentials, raw-data
folders, uploads, or local artifacts.

## Prerequisites

- Docker Engine and Docker Compose v2.
- Running Compose `db` and `qdrant` services.
- Bash, `python3`, `tar`, and `sha256sum` on the host.
- Network access to pull the temporary `curlimages/curl:8.12.1` helper image (or set
  `QDRANT_CURL_IMAGE` to an approved compatible image).

Start services:

```bash
docker compose up -d db qdrant
```

Qdrant has no published host port. The scripts inspect the running Compose Qdrant container,
identify its Docker network, and run a short-lived curl container on that network. The
temporary container is removed automatically by Docker when the request exits. The default
internal URL is `http://qdrant:6333`; do not set it to localhost or publish port 6333.

## Create a backup

```bash
chmod +x scripts/backup-local.sh scripts/restore-local.sh
./scripts/backup-local.sh
```

The default output is `backups/mfa-backup-<UTC timestamp>.tar.gz`, with an adjacent
`.sha256` file. The archive contains a PostgreSQL custom-format dump, an optional Qdrant
collection snapshot, a format-versioned manifest and payload SHA-256 checksums. The backup
script validates the PostgreSQL dump, validates the downloaded Qdrant snapshot is non-empty,
validates the tar archive, and only then publishes the completed archive. It deletes the
temporary Qdrant-side snapshot after download.

Configure retention and output:

```bash
BACKUP_DIR="$HOME/mfa-backups" BACKUP_KEEP=14 ./scripts/backup-local.sh
```

Set `BACKUP_KEEP=0` to disable pruning. Set `QDRANT_API_KEY` only if the private Qdrant
service requires it. The key is passed to the temporary helper as an environment variable,
not embedded in the request URL.

## Restore

Restoration replaces objects in the target PostgreSQL database and restores or clears the
configured Qdrant collection to match the archive. Before any destructive operation, the
script verifies the archive checksum (when present), rejects unsafe archive paths, validates
all payload checksums, validates the PostgreSQL dump, confirms the database name, checks the
Qdrant service and snapshot version compatibility, and requires typing `RESTORE`.

```bash
./scripts/restore-local.sh backups/mfa-backup-YYYYMMDDTHHMMSSZ.tar.gz
```

For deliberate non-interactive use:

```bash
./scripts/restore-local.sh /path/to/mfa-backup.tar.gz --yes
```

A successful command sequence is not proof of recoverability. Run a restore against disposable
PostgreSQL/Qdrant services and verify API readiness, a known database record, collection
existence and document search before relying on the process.

## Recovery boundaries

- Backups do not include `.env`, credentials, uploaded documents, raw-data files or ignored
  `data/` and `artifacts/` directories.
- Qdrant collection snapshots do not include aliases.
- Restore only to a Qdrant version supported by the source snapshot; the script enforces the
  same minor version at the same/newer patch or the next minor version.
- Archives may contain personal financial transaction data. Files are owner-only but not
  encrypted; protect and encrypt them before external storage.
- PostgreSQL and Qdrant snapshots are not an atomic cross-service transaction. Pause ingestion
  and indexing during backup for the strongest consistency.

Official references:
- [Qdrant snapshots](https://qdrant.tech/documentation/snapshots/).
- [Qdrant snapshot upload API](https://api.qdrant.tech/v-1-13-x/api-reference/snapshots/recover-from-uploaded-snapshot).
