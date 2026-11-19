# pipesor-rag-retrieval

RAG Retrieval supplies authorized contextual knowledge to the recommendation service through semantic search, preserving provenance and owning the knowledge context in PostgreSQL/pgvector. Its canonical architecture ID is `rag_retrieval`; the planned runtime is Python / FastAPI on Azure Container Apps.

The executable service provides a versioned internal retrieval API, explicit
authorization scopes, provenance-preserving results, PostgreSQL/pgvector persistence,
Microsoft Entra workload authentication, deterministic local adapters, an Azure
OpenAI embedding adapter, tests, a non-root container and quality automation. Live
cloud values, access grants, corpus authorization and deployment remain external
activation requirements.

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

The `X-Pipesor-Caller: recommendation_service` check is restricted to local/test.
Non-local environments use single-tenant Microsoft Entra app-only access tokens with
an exclusive RAG audience. RAG validates the RS256 signature against the tenant's
published keys, issuer, audience, lifetime, tenant, `idtyp=app`, Recommendation's
`azp` client ID and the `Rag.Query` application role; delegated tokens are rejected.

The internal endpoint is `POST /internal/v1/retrieval/query`. It accepts contract
version `1.0`, a correlation ID, query, authorization scope, permitted corpus kinds
and `top_k`. No match is a successful response with `status: no_match` and an empty
list. Results always include document/chunk identifiers and provenance.
The versioned machine-readable contract is committed at
`docs/openapi/internal-v1.json`; runtime documentation endpoints remain disabled.
After an intentional API change, regenerate and verify it with:

```bash
python tools/export_openapi.py
python tools/export_openapi.py --check
```

`PIPESOR_RAG_STORAGE_BACKEND=postgresql` selects the bounded PostgreSQL adapter
and requires `PIPESOR_RAG_DATABASE_URL`; the value is treated as a secret and must
not be logged. `PIPESOR_RAG_CANDIDATE_LIMIT` defaults to 1000. The Alembic migration
owns only the `knowledge` schema and requires the database administrator to enable
the `vector` extension first. Apply it only through an authorized migration path:

```bash
PIPESOR_RAG_DATABASE_URL='<approved Entra-compatible URL>' alembic upgrade head
```

For the hosted runtime, use a password-free URL of the form
`postgresql+psycopg://<entra-role>@<server>.postgres.database.azure.com/<database>`.
The ACA system-assigned identity obtains a PostgreSQL Entra token for each new
physical pooled connection. The runtime verifies the server hostname with the
container's system trust store. Keep its SQL role read-only on `knowledge`.
The separate migration and import commands still require their own approved
Entra-authenticated connection and role.

The approved embedding contract uses `text-embedding-3-small` with exactly 1536
dimensions for documents and queries. PostgreSQL filters by authorization scope and
compatible model version before using a cosine HNSW index. A model-version change
requires an explicit re-import/re-embedding migration; incompatible vectors are
rejected rather than mixed.

`PIPESOR_RAG_EMBEDDING_BACKEND=azure_openai` selects the Azure OpenAI v1 adapter and
requires `PIPESOR_RAG_AZURE_OPENAI_ENDPOINT`,
`PIPESOR_RAG_AZURE_OPENAI_DEPLOYMENT` and a non-placeholder
`PIPESOR_RAG_EMBEDDING_MODEL_VERSION`. The proposed dev deployment name is
`pipesor-dev-embeddings`. Authentication uses `DefaultAzureCredential`, resolving to
the Container App system-assigned identity in Azure, with the
`Cognitive Services OpenAI User` role supplied outside this repository.

The embedding operation has a total 15-second budget and at most two retries for
transient connection, timeout, throttling and server failures. The SDK retry layer is
disabled so only this adapter retries, and `Retry-After` is honored within the total
budget. Endpoint, deployment, region and quota remain environment validation inputs;
no Azure resource or role assignment is created by this repository.

### DEV workload handoff

Use the published private GHCR image by digest with internal ACA HTTPS ingress.
The container listens on port 8080 and exposes `/health/live` and
`/health/ready`. Azure private DNS must resolve the PostgreSQL server from the
workload subnet. The runtime has no Service Bus dependency.

| Source | Runtime settings |
| --- | --- |
| DEV environment | `PIPESOR_RAG_ENVIRONMENT=dev`, `PIPESOR_RAG_STORAGE_BACKEND=postgresql`, `PIPESOR_RAG_DATABASE_URL` |
| Entra workload contract | `PIPESOR_RAG_AUTHENTICATION_MODE=entra`, `PIPESOR_RAG_ENTRA_TENANT_ID`, `PIPESOR_RAG_ENTRA_AUDIENCE`, `PIPESOR_RAG_ENTRA_RECOMMENDATION_CLIENT_ID` |
| Foundry handoff | `PIPESOR_RAG_EMBEDDING_BACKEND=azure_openai`, `PIPESOR_RAG_AZURE_OPENAI_ENDPOINT`, `PIPESOR_RAG_AZURE_OPENAI_DEPLOYMENT`, `PIPESOR_RAG_EMBEDDING_MODEL_VERSION` |

Before activation, the database operator enables `vector` and the separate
migration role applies Alembic through head `20261116_03`. The authorized
import role loads eligible knowledge with the same embedding model and version.
Bind the RAG system identity to the read-only SQL role and grant it
`Cognitive Services OpenAI User` on the Foundry account. Assign `Rag.Query`
on the exclusive RAG audience to the Recommendation app identity. Confirm
private GHCR pull credentials and verify readiness and an authenticated query
from Recommendation in DEV after the target receives deployment authorization.

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
Local/test defaults remain deterministic simulations with the same 1536-dimension
shape. Real corpus remains prohibited until its inventory, provenance, sanitization,
scope and accountable authorization are recorded.

## Runtime safety

`/health/live` reports process survival. `/health/ready` checks the selected
knowledge repository and returns `503 not_ready` when PostgreSQL cannot answer.
Requests default to a 64 KiB limit (`PIPESOR_RAG_MAX_REQUEST_BYTES`). Operational
logs are JSON and contain only route/method/status/duration and the opaque
correlation header, never query or retrieved content.

Authentication is fail-closed by environment. `simulated` is allowed only with
`PIPESOR_RAG_ENVIRONMENT=local|test`; non-local startup rejects it. `entra` requires
`PIPESOR_RAG_ENTRA_TENANT_ID`, `PIPESOR_RAG_ENTRA_AUDIENCE` and
`PIPESOR_RAG_ENTRA_RECOMMENDATION_CLIENT_ID`. The required role is fixed to
`Rag.Query`. IaC must create the app role/audience and assign it to Recommendation's
system-assigned identity; this repository creates no identity or role assignment.

CI applies the real Alembic chain to a disposable PostgreSQL 17/pgvector service
pinned by digest. It verifies import creation/idempotency/replacement, active-version
selection, tenant/repository isolation and readiness. Runtime database connection
and pool waits default to five seconds and are bounded by
`PIPESOR_RAG_DATABASE_CONNECT_TIMEOUT_SECONDS` and
`PIPESOR_RAG_DATABASE_POOL_TIMEOUT_SECONDS`.

## Image publication and assurance

Pull requests build and inspect the service image without registry credentials.
Every push to `main` repeats the complete quality suite, builds one image and exports
that verified artifact. Only after that job succeeds does a separate least-privilege
job publish the exact artifact to the private package:

```text
ghcr.io/pipesor-org/pipesor-rag-retrieval:sha-<full-commit-sha>
```

The publication job resolves the registry digest, verifies that the package remains
private and retains `<image>@sha256:<digest>` as delivery evidence. Consumers and
deployments must use that digest, not a mutable tag. The manually dispatched
`Promote release image` workflow accepts an existing digest and a `vX.Y.Z` tag,
then attaches that tag without rebuilding and verifies that the digest is unchanged.

CI produces CycloneDX SBOMs for Python dependencies and the complete container image,
plus JSON vulnerability reports. `pip-audit` findings fail its dependency audit. The
container policy blocks publication on every `CRITICAL` operating-system or
language-package vulnerability and every `HIGH` vulnerability for which a fix is
available. Unfixed `HIGH` findings and all `LOW`, `MEDIUM` and `UNKNOWN` findings
remain in the complete report for risk review but do not block this increment. The
runtime image removes `pip` after installation to avoid shipping its unused vendored
build dependencies.

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
