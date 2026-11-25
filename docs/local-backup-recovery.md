# Local backup and recovery

This project runs as a personal, single-node Docker Compose workspace. The local backup
workflow protects the PostgreSQL application database and the configured Qdrant collection.
It does not copy API credentials or the repository's ignored raw-data/artifact folders.

## Prerequisites

- Docker Engine and Docker Compose v2.
- The Compose `db` and `qdrant` services running.
- `curl`, `python3`, `tar`, and `sha256sum` on the host.
- Bash (Linux/macOS, or Git Bash on Windows).

Start the local services first:

```bash
docker compose up -d db qdrant
```

The scripts use the Compose database container's `POSTGRES_DB` and `POSTGRES_USER`
environment values and do not expose the password in command-line arguments. Qdrant is
accessed through `http://localhost:6333` by default.

## Create a backup

```bash
chmod +x scripts/backup-local.sh scripts/restore-local.sh
./scripts/backup-local.sh
```

The default output is `backups/mfa-backup-<UTC timestamp>.tar.gz`, plus an adjacent
`.sha256` file. The archive contains:

- A PostgreSQL custom-format dump.
- A Qdrant collection snapshot if the configured collection exists.
- A JSON manifest with backup time, database/collection names, Qdrant version, and source
  Git commit.
- A `SHA256SUMS` file covering every payload in the archive.

The script downloads and then removes its temporary Qdrant-side snapshot. The default
retention is the newest seven archives. Set `BACKUP_KEEP=0` to disable automatic pruning,
or configure a different retention count with:

```bash
BACKUP_DIR="$HOME/mfa-backups" BACKUP_KEEP=14 ./scripts/backup-local.sh
```

The Qdrant defaults are `QDRANT_URL=http://localhost:6333` and
`QDRANT_COLLECTION=mutual_fund_research`. Override them with exported environment variables
when the local API uses a different collection or endpoint. Set `QDRANT_API_KEY` only when
the Qdrant server itself requires API-key authentication.

## Restore a backup

Restoration is destructive. It replaces objects in the target PostgreSQL database and
overwrites the configured Qdrant collection. The script:

1. Verifies the archive's adjacent checksum (when present), validates archive paths, and
   verifies each payload checksum.
2. Checks the archive paths and entry types before extraction.
3. Checks that the target Compose database name matches the database recorded in the manifest.
4. Checks Qdrant snapshot compatibility and SHA-256 before changing database contents.
5. Requires the exact interactive confirmation word `RESTORE`.
6. Restores PostgreSQL, restores or clears the Qdrant collection to match the backup, and
   applies any newer Alembic migrations.

Run:

```bash
./scripts/restore-local.sh backups/mfa-backup-YYYYMMDDTHHMMSSZ.tar.gz
```

For a deliberately scripted restore, pass `--yes` explicitly:

```bash
./scripts/restore-local.sh /path/to/mfa-backup.tar.gz --yes
```

Do not use `--yes` unless you have verified the archive and intend to overwrite the current
local data. For a different target database name, update the local Compose configuration
deliberately rather than bypassing the database-name check.

## Recovery boundaries

- Backups cover PostgreSQL and one Qdrant collection, not `.env`, provider credentials,
  local uploads, downloaded source files, or ignored `data/` and `artifacts/` directories.
  Store secrets separately and back up user-owned files separately where needed.
- Qdrant collection snapshots contain the collection configuration, points, and payloads;
  collection aliases are not included. The app currently configures one research collection.
- Qdrant snapshots can only be restored to a compatible release: the same minor version at
  the same or a newer patch, or the next minor version. Keep the Compose Qdrant image pinned
  until recovery is complete.
- Archives contain personal financial transaction data. The scripts create new files with
  owner-only permissions, but they do not encrypt archives; store them on a protected disk and
  encrypt them before copying to external or cloud storage.
- PostgreSQL and Qdrant snapshots are not an atomic cross-service transaction. Pause ingestion
  and document indexing while creating a backup for the strongest consistency.
- A backup is not proven recoverable until a restore has been performed. Before relying on
  this workflow, run one restore against a disposable local copy and verify health checks,
  a known database row, and a document search.

Official references:
- [Qdrant snapshots](https://qdrant.tech/documentation/snapshots/) — collection snapshot,
  download, uploaded restore, and supported version window.
- [Qdrant snapshot upload API](https://api.qdrant.tech/v-1-14-x/api-reference/snapshots/recover-from-uploaded-snapshot).
