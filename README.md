# pipesor-rag-retrieval

RAG Retrieval supplies authorized contextual knowledge to the recommendation service through semantic search, preserving provenance and owning the knowledge context in PostgreSQL/pgvector. Its canonical architecture ID is `rag_retrieval`; the planned runtime is Python / FastAPI on Azure Container Apps.

The first executable increment provides a versioned internal retrieval API, explicit
authorization scopes, provenance-preserving results, deterministic local adapters,
tests, a non-root container and quality automation. PostgreSQL/pgvector, Entra and
Microsoft Foundry remain behind interfaces until their open contracts are approved.

## Documentation

- [Documentation baseline](docs/documentation-baseline.md): audited source revisions, evidence limits and adoption after merge.

- [Architecture](docs/architecture.md): service boundaries, integration context and current sources in `pipesor-docs`.
- [Deployment contract](docs/deployment-contract.md): development baseline, delivery requirements and unresolved contracts.
- [AGENTS.md](AGENTS.md): repository instructions for coding agents.

## Development and verification

The [development baseline](docs/deployment-contract.md#development-baseline) records the selected toolchain and dependency policy. Use Python 3.14 in an isolated environment:

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pytest
python -m compileall -q src tests tools
alembic upgrade head --sql
python -m pipesor_rag_retrieval.main
```

The service binds to `0.0.0.0:8080` by default. `PIPESOR_RAG_HOST` and
`PIPESOR_RAG_PORT` override those values. Build and run the container with:

```bash
docker build --provenance=false --tag pipesor-rag-retrieval:local .
docker run --rm --publish 8080:8080 pipesor-rag-retrieval:local
```

The current `X-Pipesor-Caller: recommendation_service` check is a deliberately
isolated adapter for local contract validation. It is not production authentication;
the approved Entra audience/application contract must replace it before deployment.

The internal endpoint is `POST /internal/v1/retrieval/query`. It accepts contract
version `1.0`, a correlation ID, query, authorization scope, permitted corpus kinds
and `top_k`. No match is a successful response with `status: no_match` and an empty
list. Results always include document/chunk identifiers and provenance.

`PIPESOR_RAG_STORAGE_BACKEND=postgresql` selects the bounded PostgreSQL adapter
and requires `PIPESOR_RAG_DATABASE_URL`; the value is treated as a secret and must
not be logged. `PIPESOR_RAG_CANDIDATE_LIMIT` defaults to 1000. The Alembic migration
owns only the `knowledge` schema and requires the database administrator to enable
the `vector` extension first. Apply it only through an authorized migration path:

```bash
PIPESOR_RAG_DATABASE_URL='<approved Entra-compatible URL>' alembic upgrade head
```

The current adapter filters by authorization scope before loading a bounded set of
vectors. It deliberately creates no vector index; production semantic search remains
blocked on the approved embedding model and dimension.

## Administrative corpus import

Corpus loading is an administrative CLI, not an HTTP API. Input must be sanitized
JSON with canonical `github_installation_id` / `github_repository_id`, provenance,
an authorization reference, source ID/version and non-evaluation chunks. Run it only
through an approved database access path:

```bash
PIPESOR_RAG_STORAGE_BACKEND=postgresql \
PIPESOR_RAG_DATABASE_URL='<approved Entra-compatible URL>' \
pipesor-rag-import authorized-document.json
```

The same source version and canonical hash is idempotent. Reusing a version with
different content fails; a new version deactivates the former active version.
Embeddings remain deterministic simulations until Foundry model, dimension,
deployment, region and permissions are approved.

## Runtime safety

`/health/live` reports process survival. `/health/ready` checks the selected
knowledge repository and returns `503 not_ready` when PostgreSQL cannot answer.
Requests default to a 64 KiB limit (`PIPESOR_RAG_MAX_REQUEST_BYTES`). Operational
logs are JSON and contain only route/method/status/duration and the opaque
correlation header, never query or retrieved content.

Authentication is fail-closed by environment. `simulated` is allowed only with
`PIPESOR_RAG_ENVIRONMENT=local|test`; non-local startup rejects it. Selecting
`entra` also fails until issuer, audience, role and managed-identity values are
approved and its adapter is implemented.

Check affected links and consistency with the referenced sources, then run:

```bash
git diff --check
```

For TOML configuration changes, run this syntax check with Python 3.11+ (the selected Python baseline supports `tomllib`):

```bash
python3 -c 'from pathlib import Path; import tomllib; [tomllib.loads(p.read_text()) for p in Path(".codex").rglob("*.toml")]; print("TOML syntax OK")'
```

Follow the organization [contribution policy](https://github.com/pipesor-org/.github/blob/main/CONTRIBUTING.md), [code of conduct](https://github.com/pipesor-org/.github/blob/main/CODE_OF_CONDUCT.md) and [security policy](https://github.com/pipesor-org/.github/blob/main/SECURITY.md). Licensing remains pending.

## Optional Codex setup

Start Codex from this repository root so its [repository instructions](AGENTS.md) are discovered. Project configuration is in [.codex/config.toml](.codex/config.toml); [rag_reviewer](.codex/agents/rag-reviewer.toml) defines a focused reviewer. Review roles do not create separate sandbox permissions.

After changing instructions, start a fresh session and ask it to identify its active instruction sources. See the official [instruction-discovery guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and [subagent guide](https://learn.chatgpt.com/docs/agent-configuration/subagents). A successful TOML parse alone does not establish live discovery or reviewer execution.
