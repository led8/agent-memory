#!/usr/bin/env bash
#
# Online APOC backup of the agent-memory Neo4j corpus.
#
# Output: ~/.agent-memory-backups/agent-memory-YYYYMMDD-HHMMSS.cypher
# Retention: keeps the most recent 30 backups, deletes older ones.
#
# Usage:
#   ./scripts/backup_agent_memory.sh                    # default container
#   NEO4J_CONTAINER=other ./scripts/backup_agent_memory.sh
#
# Required env (or .env in cwd):
#   NEO4J_PASSWORD   Neo4j password
# Optional env:
#   NEO4J_USERNAME   default: neo4j
#   NEO4J_CONTAINER  default: neo4j-agent-memory-test
#   BACKUP_DIR       default: ~/.agent-memory-backups
#   RETENTION        default: 30 (most recent N backups kept)

set -euo pipefail

# Load .env from current dir if present (for NEO4J_PASSWORD)
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

NEO4J_USERNAME="${NEO4J_USERNAME:-neo4j}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-neo4j-agent-memory-test}"
BACKUP_DIR="${BACKUP_DIR:-${HOME}/.agent-memory-backups}"
RETENTION="${RETENTION:-30}"

if [[ -z "${NEO4J_PASSWORD:-}" ]]; then
    echo "ERROR: NEO4J_PASSWORD not set (env var or .env)" >&2
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "^${NEO4J_CONTAINER}\$"; then
    echo "ERROR: container '${NEO4J_CONTAINER}' is not running" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"
TS=$(date +%Y%m%d-%H%M%S)
OUT="${BACKUP_DIR}/agent-memory-${TS}.cypher"

echo "Backing up ${NEO4J_CONTAINER} → ${OUT}"

# APOC online export. --format plain strips the cypher-shell ascii-table.
docker exec "${NEO4J_CONTAINER}" cypher-shell \
    -u "${NEO4J_USERNAME}" -p "${NEO4J_PASSWORD}" \
    "CALL apoc.export.cypher.all(null, {stream:true, format:'plain'}) YIELD cypherStatements RETURN cypherStatements" \
    --format plain > "${OUT}"

# Strip the leading "cypherStatements" header line and surrounding quotes
# emitted by cypher-shell so the file is directly replayable.
python3 - "${OUT}" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
raw = p.read_text()
lines = raw.splitlines()
# Drop "cypherStatements" header and any trailing blank lines.
if lines and lines[0].strip() == "cypherStatements":
    lines = lines[1:]
text = "\n".join(lines).strip()
# cypher-shell wraps the multi-line value in double quotes and escapes inner ones.
if text.startswith('"') and text.endswith('"'):
    text = text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
p.write_text(text + "\n")
PY

# Guard: refuse to keep an empty / trivial backup
SIZE=$(wc -c < "${OUT}")
if [[ "${SIZE}" -lt 50 ]]; then
    echo "WARNING: backup is suspiciously small (${SIZE} bytes). Keeping it anyway: ${OUT}" >&2
fi

echo "  ${SIZE} bytes, $(wc -l < "${OUT}") lines"

# Retention: keep newest N, delete older
mapfile -t OLD < <(ls -1t "${BACKUP_DIR}"/agent-memory-*.cypher 2>/dev/null | tail -n +$((RETENTION + 1)))
if [[ ${#OLD[@]} -gt 0 ]]; then
    echo "Pruning ${#OLD[@]} old backup(s) (retention=${RETENTION})"
    rm -f "${OLD[@]}"
fi

echo "OK"
