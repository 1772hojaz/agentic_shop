#!/bin/sh
# Back up PostgreSQL and product uploads; keep secrets out of the archive.
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T db sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
    > "backups/database-$stamp.dump"
docker compose exec -T api tar czf - -C /app uploads \
    > "backups/uploads-$stamp.tar.gz"
printf 'Backup completed: %s\n' "$stamp"
