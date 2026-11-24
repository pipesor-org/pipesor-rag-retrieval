# pipesor-rag-retrieval

RAG Retrieval supplies authorized contextual knowledge to the recommendation service through semantic search, preserving provenance and owning the knowledge context in PostgreSQL/pgvector. Its canonical architecture ID is `rag_retrieval`; the planned runtime is Python / FastAPI on Azure Container Apps.

The executable service provides a versioned internal retrieval API, explicit
authorization scopes, provenance-preserving results, PostgreSQL/pgvector persistence,
platform workload JWT authentication (with Entra as an alternative), test-only deterministic
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

The service uses `SERVER_ADDRESS` and `SERVER_PORT` from the runtime manifest
(`127.0.0.1:8087` locally and `0.0.0.0:8080` in Azure). Build the container with:

```bash
docker build --provenance=false --tag pipesor-rag-retrieval:local .
docker run --rm --publish 8080:8080 pipesor-rag-retrieval:local
```

Runtime requests use `Authorization: Bearer <token>`. Platform mode validates the
Recommendation JWKS and exact `platform-identity-v1` claims: RS256, the canonical
issuer/audience/tenant/workload identity, app token type, version 2.0, lifetime no
greater than 300 seconds, no `scp`, and the sole `Rag.Query` role. Entra remains an
explicit alternative. `X-Pipesor-Caller` exists only in automated tests.

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

Runtime selects PostgreSQL and requires `PIPESOR_DATABASE_URL`; the value is treated
as a secret and must not be logged. Local mode also consumes
`PIPESOR_DATABASE_USERNAME` and `PIPESOR_DATABASE_PASSWORD`; Azure uses managed
identity. Memory storage is rejected outside automated tests. The Alembic migration
owns only the `knowledge` schema and requires the database administrator to enable
the `vector` extension first. Apply it only through an authorized migration path:

```bash
PIPESOR_DATABASE_URL='<approved Entra-compatible URL>' alembic upgrade head
```

For the hosted runtime, use a password-free URL of the form
`postgresql+psycopg://<entra-role>@<server>.postgres.database.azure.com/<database>`.
The ACA system-assigned identity obtains a PostgreSQL Entra token for each new
physical pooled connection. The runtime verifies the server hostname with the
container's system trust store. Keep its SQL role read-only on `knowledge`.
The separate migration and import commands still require their own approved
Entra-authenticated connection and role.

The approved embedding contract uses `text-embedding-3-small` with exactly 1536
dimensions for documents and queries. PostgreSQL filters by authorization scope,
corpus kind and model version, orders by cosine distance and applies `LIMIT top_k`
in SQL. Each query sets `hnsw.ef_search` and `statement_timeout`; the distance is not
recalculated in Python. A model-version change
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
| Runtime | `PIPESOR_ENVIRONMENT=local|azure`, `SERVER_ADDRESS`, `SERVER_PORT`, `PIPESOR_DATABASE_URL`, and local database credentials |
| Platform workload contract | `PIPESOR_RAG_AUTHENTICATION_MODE=platform`, `PIPESOR_TENANT_ID`, `PIPESOR_SECURITY_AUDIENCE`, and `PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_*` |
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
PIPESOR_ENVIRONMENT=azure \
PIPESOR_DATABASE_URL='<approved Entra-compatible URL>' \
pipesor-rag-import authorized-document.json
```

The same source version and canonical hash is idempotent. Reusing a version with
different content fails; a new version deactivates the former active version.
Deterministic embeddings are test-only. Real corpus remains prohibited until its
inventory, provenance, sanitization,
scope and accountable authorization are recorded.

## Runtime safety

`/health/live` reports process survival. `/health/ready` checks PostgreSQL and that
Alembic is at head `20261116_03`, returning `503 not_ready` on failure.
Requests default to a 64 KiB limit (`PIPESOR_RAG_MAX_REQUEST_BYTES`). Operational
logs are JSON and contain only route/method/status/duration and the opaque
correlation header, never query or retrieved content.

Authentication is fail-closed by environment. Test authentication is rejected in
both `local` and `azure`; `entra` requires
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

Two query controls are not yet named by the shared runtime manifest and must be
added before deployment: `PIPESOR_RAG_DATABASE_STATEMENT_TIMEOUT_MS` (default
`5000`) and `PIPESOR_RAG_HNSW_EF_SEARCH` (default `100`).

## CI/CD and image assurance

[CI](.github/workflows/ci.yml) calls the shared [`service-ci.yml`](https://github.com/pipesor-org/pipesor-ci#catalog)
from [pipesor-ci](https://github.com/pipesor-org/pipesor-ci), pinned by commit SHA (Dependabot proposes updates):

1. **Conventions**: canonical commitlint/Lefthook, PR title (at most 65 characters) and description, Conventional
   Commits, actionlint and zizmor. Install the commit hook with `bun install --frozen-lockfile && bun run setup:hooks`.
2. **Build**: [`tools/ci_verify.sh`](tools/ci_verify.sh) runs the unit suite, `compileall`, the committed OpenAPI
   contract check, offline migration rendering and the PostgreSQL/pgvector integration suite against a disposable
   container (run it locally with Docker the same way). The image is built once and
   [`tools/check_image.py`](tools/check_image.py) verifies UID/GID `10001`, the single `8080/tcp` port, offline
   migrations inside the image, liveness with platform authentication settings and a clean `SIGTERM` stop.
3. **Image assurance**: Trivy records the complete image SBOM and vulnerability report (90-day evidence) and blocks
   every `HIGH` or `CRITICAL` vulnerability with an available fix; unfixed findings stay in the report for risk
   review. Reviewed exceptions belong in `.trivyignore.yaml`. The runtime image removes `pip` after installation to
   avoid shipping its unused vendored build dependencies.
4. **Publish** (pushes to `main` only): the exact tested archive is pushed to the private package as
   `ghcr.io/pipesor-org/pipesor-rag-retrieval:sha-<commit>-<run>-<attempt>`, and `candidate.json` records the source
   SHA, digest and CI run/attempt. Consumers and deployments use the digest, never a mutable tag.

This repository does not deploy: the environment's Terraform root in
[pipesor-iac](https://github.com/pipesor-org/pipesor-iac/blob/main/docs/dev-runtime-deployment.md) pins the image by
digest. [Release candidate](.github/workflows/release.yml) is hard-disabled; when activated it names an existing
digest `vX.Y.Z[-rc.N]` through a GitHub Release, without registry retagging or rebuilding.

**Registry retention.** [Registry retention](.github/workflows/registry-retention.yml) runs weekly through the shared [pipesor-ci workflow](https://github.com/pipesor-org/pipesor-ci#registry-retention): it keeps every deployed or recently deployed digest (pipesor-iac `images.json` history), release digests, the newest and recent candidates and the children of kept image indexes, and reports the rest. It is a dry run until the repository variable `REGISTRY_RETENTION_DELETE` is `true`.

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
