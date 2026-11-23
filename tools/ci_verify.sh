#!/usr/bin/env bash
# Repository verification used by CI and locally (needs Docker): unit tests, OpenAPI and offline
# migration checks, then the PostgreSQL/pgvector integration suite against a disposable container
# published on a random localhost port.
set -euo pipefail

PGVECTOR_IMAGE="pgvector/pgvector:pg17@sha256:b513c48566e4777cd3370451400000c78eda6a08131d68f4c31d4a76f27bd8fd"

python -m pip install --disable-pip-version-check -e ".[dev]"
python -m pytest
python -m compileall -q src tests tools
python tools/export_openapi.py --check
alembic upgrade head --sql > /dev/null

name="pipesor-rag-ci-$$"
docker run --detach --name "$name" --publish 127.0.0.1::5432 \
  --env POSTGRES_USER=pipesor --env POSTGRES_PASSWORD=pipesor-test-only --env POSTGRES_DB=pipesor_rag \
  --health-cmd "pg_isready -U pipesor -d pipesor_rag" --health-interval 2s --health-timeout 5s --health-retries 30 \
  "$PGVECTOR_IMAGE" > /dev/null
trap 'docker rm --force "$name" > /dev/null 2>&1 || true' EXIT
for _ in $(seq 1 60); do
  [ "$(docker inspect --format '{{.State.Health.Status}}' "$name")" = healthy ] && break
  sleep 1
done
test "$(docker inspect --format '{{.State.Health.Status}}' "$name")" = healthy
port="$(docker port "$name" 5432/tcp | head -n 1 | sed 's/.*://')"

export PIPESOR_DATABASE_URL="postgresql+psycopg://pipesor:pipesor-test-only@127.0.0.1:${port}/pipesor_rag"
export PIPESOR_RAG_TEST_DATABASE_URL="$PIPESOR_DATABASE_URL"
python -c "import psycopg, sys; c = psycopg.connect(sys.argv[1]); c.execute('CREATE EXTENSION IF NOT EXISTS vector'); c.commit()" \
  "postgresql://pipesor:pipesor-test-only@127.0.0.1:${port}/pipesor_rag"
alembic upgrade head
python -m pytest tests/test_postgres_integration.py
