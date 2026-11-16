# Deployment contract: rag_retrieval

## Authorized first local increment

The project owner authorized this local increment on 2026-11-11 with a versioned
REST contract, scoped authorization and configurable simulated/Azure embeddings,
without real data or Azure resources. This authorization does not approve IaC
consumption or deployment.

- Internal route: `POST /internal/v1/retrieval/query`, contract version `1.0`.
- Only `recommendation_service` is the intended caller.
- Scope includes tenant, GitHub installation, repository, optional pipeline and
  authorization revision, and is applied before results leave the service.
- Results preserve document ID, chunk ID, corpus kind and provenance; `no_match`
  remains distinct from validation, authorization and dependency failures.
- Deterministic embeddings, in-memory knowledge and the caller header are local/test
  adapters, not production security or semantic-search implementations.
- The approved v0.1 contract selects `text-embedding-3-small`, 1536 dimensions,
  Azure OpenAI API v1, system-assigned managed identity and the
  `Cognitive Services OpenAI User` requirement. Region, live deployment validation,
  quota, endpoint values, role assignment and cloud activation remain separate.

The PostgreSQL foundation added after the initial API owns Alembic migrations for
`knowledge.knowledge_documents` and `knowledge.knowledge_chunks`. It adds explicit
tenant/installation/repository/pipeline/revision scope columns, an internal document
foreign key and a scope index. It neither creates the database-level `vector`
extension nor creates a vector index. Runtime selection is explicit through
`PIPESOR_RAG_STORAGE_BACKEND`; PostgreSQL additionally requires a secret database
URL and a separately authorized Entra-compatible access path.

The 2026-11-16 approval adopts canonical GitHub identity names for the
Recommendation-to-RAG v1 scope and an administrative, idempotent corpus importer.
Recommendation supplies a previously verified scope; RAG authenticates that caller
and applies a second scope filter. The import CLI requires source/version/hash,
provenance and authorization evidence, rejects evaluation material and exposes no
public loading API. Azure embeddings are selectable through the approved v0.1
adapter; live endpoint, region, quota and RBAC validation remain deployment inputs.

The local runtime increment distinguishes liveness from repository readiness,
limits request bytes, emits content-free JSON operational logs and maps unavailable
retrieval dependencies to a generic retryable `503`. Simulated caller identity is
limited to local/test; every non-local environment requires the approved Entra
tenant, audience, Recommendation client identity and `Rag.Query` role contract.

**Status: executable and publishable service artifact; not approved for IaC activation or deployment.** Prepared for PD-035. [Architecture consumption](architecture.md) records the consulted source revision `c84ef3e4629fcb0c38315f32b641a5fb949e450d`, model IDs, applicable ADRs and committed PD-033–036. ADR-019 governs the current MVP alignment.

**Documented fact** means recorded in those sources/policies, not proven implementation or independent approval evidence. **Proposal** requires acceptance; **Unknown** remains pending. This repository now includes executable application code, owned Alembic migrations, an image definition and private publication automation. The first successful merged-main run supplies the published digest. No credentials, cloud resources or deployment are created here. IaC contains infrastructure preparation; provisioning is not evidenced here.

## Identity and runtime

| Requirement | Value | Source and status |
|---|---|---|
| Identity and responsibility | `rag_retrieval` — Retrieve authorized contextual knowledge through semantic search, preserve provenance and own the knowledge context in PostgreSQL/pgvector. | Documented fact: `elements[rag_retrieval]`, ADR-018. |
| Independent deployment | Yes; separate backend repository/container on Microsoft Azure Container Apps. | Documented fact: `deployment.container_hosts.rag_retrieval`, ADR-001/015/018 as applicable. No deployed service resource is evidenced by this repository. |
| Language/framework | Python / FastAPI. | Documented fact: element `backend`, ADR-018. See the session-authorized development baseline below. Dependency pins and base-image selection remain implementation/delivery requirements under PD-032/035. |

## Development baseline

User direction recorded on 2026-11-06 retains the installed Java 25.0.4.1, Python 3.14.8, Docker 29.9.3 and Git 2.55.0. Java services use Maven (installed: 3.10.0); Azure CLI 2.92.0 is available for separately authorized operations. Select the latest stable dependency versions compatible with that baseline, and pin them when application build/dependency files are introduced. Framework and transitive dependency compatibility must be checked together; availability on this workstation is not container/CI verification. Python dependencies belong in isolated project environments.

This session direction supplements the consulted architecture revision; it does not close PD-032's identity/hash choices or PD-035's base-image and delivery requirements. No application build files are introduced by this documentation update.

## Integrated infrastructure baseline

The [IaC resource baseline](https://github.com/pipesor-org/pipesor-iac/blob/main/docs/mvp-resource-baseline.md) at `pipesor-iac@4b42c0c8e66578dfb890ae1cca8c9c31c774026e` selects GHCR and system-assigned identity per future Container App. Identity is created with its app; it is not an existing identity or a scoped access grant. The [native-ingress decision](https://github.com/pipesor-org/pipesor-iac/blob/main/docs/adr-003-mvp-native-ingress.md) preserves service-side authorization, and [ADR 004](https://github.com/pipesor-org/pipesor-iac/blob/main/docs/adr-004-mvp-state-and-deployment.md) restricts current preparation to dev with separately authorized activation and Azure actions.

Shared opt-in Terraform foundations include the external-capable ACA environment/VNet, Entra-only public Service Bus Standard namespace, private Entra-only PostgreSQL 17 Flexible Server (B2s, 32 GiB, seven-day local backups, no HA), shared Log Analytics/Application Insights and public Entra-only Foundry account/project. These are approved IaC preparation choices with checked-in infrastructure code, not evidence of deployed or reachable dependencies. They do not add a database, broker or AI relationship to a service that lacks one in the architecture model.

PostgreSQL's `vector` allowlist setting does not execute SQL extension creation, schemas, migrations or grants. Broker entities/delivery semantics, SQL/token access, operator/migration connectivity, instrumentation, model/API compatibility, image pulls and required per-service contracts remain pending. Platform/database backup and telemetry retention do not implement the 365-day evidence policy. Read the [documentation baseline](documentation-baseline.md) for source and evidence limits.

## Artifact and responsibility boundary

| Requirement | Value | Source and status |
|---|---|---|
| Delivery unit | Container image for this service. | Documented fact: `deployment.containerization`, ADR-001/018. |
| Immutable identity | A successful merged-main workflow publishes the already verified image as `ghcr.io/pipesor-org/pipesor-rag-retrieval:sha-<full-commit-sha>`, records its registry digest and verifies private visibility. Consumers use the digest. | Implemented delivery contract; the first successful run supplies the concrete digest. |
| Release/version | Policy targets Conventional-Commit-derived SemVer and protected `vX.Y.Z` tags after staging, without rebuilding. The manual promotion workflow accepts an existing digest and verifies it is unchanged after tagging. | Implemented artifact promotion mechanism; version selection, Git tag protection and environment approvals remain release-governance inputs. |
| Ownership handoff | This repository supplies the tested private image/digest and runtime/configuration requirements; IaC consumes the approved digest for the agreed environment. | Implemented artifact handoff; private GHCR pull credentials and deployment authorization remain IaC/administration work. |
| Promotion responsibility | Independent QA approval before staging and independent product-owner approval before production are policy targets. | Documented organization target. Concrete automation, environment mapping and operational owners remain unknown under PD-035; do not infer them from the sibling IaC implementation. |

Current target: only `dev` is selected for temporary academic MVP preparation (ADR-019 and IaC ADR 004). Local service integration/validation, complete readiness/access/cost review and explicit target/action authorization precede Azure writes. The dev procedural approval exception does not extend to future environments; retain independent QA/production promotion rules when commissioned.

## Execution

Documented fact: Documented synchronous REST/HTTPS requests from recommendation_service (rel_recommendation_rag). No public ingress relationship is declared. Sources: service relationships listed in [architecture consumption](architecture.md), ADR-015/016/019 where applicable.

| Pending runtime value | Status and approval required |
|---|---|
| Listening port and bind address | `0.0.0.0:8080`; configurable with `PIPESOR_RAG_HOST` and `PIPESOR_RAG_PORT`. |
| Ingress scope, routing, TLS termination and caller authorization | Unknown beyond the documented caller/protocol above; PD-034/035, and PD-036 for workflow access where used. Do not add public exposure. |
| Liveness/readiness/startup probes | HTTP `/health/live` verifies process survival; `/health/ready` verifies the selected repository and returns 503 when unavailable. Probe timings remain a deployment input. |
| Startup | Initialization order, dependency retries, startup budget and migration coordination unknown, PD-035. |
| Shutdown | Graceful termination/drain behavior, time budget and in-flight work handling unknown, PD-035; broker consumers also depend on PD-033 re-delivery agreement. |

## Configuration and secrets

| Category | Known requirement and supplier | Status/source |
|---|---|---|
| Nonsecret integration settings | PostgreSQL target and authorized knowledge scope; `text-embedding-3-small`, 1536 dimensions, model version, Azure OpenAI endpoint/deployment; Entra tenant, RAG audience, Recommendation client ID and `Rag.Query`. Region, quota and concrete resource identifiers are supplied after live validation. | Approved v0.1 contract; environment values remain deployment inputs. |
| Secret/authentication requirements | System-assigned identity uses token-based Azure OpenAI access with `Cognitive Services OpenAI User`; Recommendation uses an app-only token for RAG with `Rag.Query`. PostgreSQL remains Entra-only with separate runtime/import/migration grants. No API key is accepted by the application contract. | Approved mechanisms; actual principals, grants and connectivity remain IaC/administration delivery work. |
| Delivery of values | Proposed: backend maintainers define/validate the required configuration interface; the authorized environment/integration owners supply approved values through the agreed IaC handoff. | Proposal, PD-035; specific people/teams, rotation and distribution mechanism remain unknown. |

The application environment-variable names and validated defaults are documented in
the repository README and enforced by the typed configuration. No credential value or
secret store is created here. The system-assigned ACA identity lifecycle is selected
in IaC; its creation, access grants and user/workflow authentication remain separate
requirements.

## Access and integration

| Downstream | Intended operation and boundary | Canonical source |
|---|---|---|
| `pgvector_knowledge_store` | Data plane: read/search authorized knowledge; ADR-018 assigns owned-table writes for maintenance, but ingestion/update mechanism remains PD-006. | `rel_rag_pgvector`; PostgreSQL/pgvector |

Documented fact: incoming consumers/callers are listed in [service relationships](architecture.md#service-relationships). Protocols and directional operations above describe data access, not granted permissions. Control-plane access for Azure/GitHub provisioning or administration is not part of the service runtime contract; no grants are authorized. Exact credentials, audiences, scopes, network rules and permission sets remain unknown (PD-027/034/035 and PD-036 if used). Embedding-provider descriptions do not authorize undeclared direct calls.

## Data lifecycle

Documented ownership from ADR-018 and `model/domain.yml.entities`:

`knowledge.knowledge_documents` (confirmed), `knowledge.knowledge_chunks` (confirmed)

One physical PostgreSQL instance is shared; queries and commands use logical CQRS. Writes are confined to owned tables; shared schemas do not grant cross-owner writes. Physical FKs may exist within a schema; cross-schema references are logical IDs, with no ORM navigation across contexts (ADR-018, DD-014, PD-031). `audit.audit_events` has shared cross-cutting ownership and is not assigned exclusively to this repository; exact shared audit-write mechanics remain pending PD-035. Inferred `pipeline_access_grants`, where listed, preserve `ia_only`/inferred status and pending PD-007/008. No persistent schema is added for technical processing services without documented ownership.

The service owns and validates its Alembic migrations for the `knowledge` schema; IaC
does not own functional schema changes. The authorized migration runner, grants,
deployment sequencing and rollback/recovery procedure remain deployment decisions.
The database administrator must enable the `vector` extension before Alembic runs.

**Documented facts:** logical references must be validated through existing contracts (PD-031). Logs, diagnoses and evidence have the documented 365-day retention policy (ADR-013/016/018, INV-009, domain RET-001); do not extend that duration to corpus, configuration or audit. Policy evidence and purge mechanisms remain PD-017/030.

The Recommendation-to-RAG REST contract is version `1.0`, and the approved embedding
contract fixes `text-embedding-3-small` at 1536 dimensions. The schema rejects
incompatible vectors and model versions. Migration rollout sequencing and validation
against live infrastructure remain deployment work; real corpus updates continue to
require the authorization and provenance rules of PD-006/023.

## Operations

Documented facts: Azure Monitor and Application Insights for application telemetry (ADR-002); correlationId, traceability and cross-cutting functional audit are model requirements (`audit_trail`, CTRL-003/004). Functional audit in PostgreSQL is distinct from technical telemetry. Evidence protection before NLP/RAG/LLM, read-only GitHub access and human control remain applicable invariants.

Unknown under PD-035: application instrumentation/token handling, log format/export, sampling, alerts, dashboards, operational ownership, SLOs, replicas, autoscaling triggers, concurrency, application CPU/memory/storage, actual region/names and availability budgets. The integrated foundation choices above do not settle those per-service contracts. Model evaluation targets are not operational SLOs. PD-029 also preserves unresolved operational degradation/version-update mechanisms for AI-related capabilities. No per-service resources or executable deployment configuration are inferred.

## Approval and unresolved decisions

Readiness blockers for the affected increment: [PD-035](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-032](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-027](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-005](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-006](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-023](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-029](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-031](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md), [PD-034](https://github.com/pipesor-org/pipesor-docs/blob/main/docs/architecture/pending-decisions.md). PD-033/034/036 apply only to the exchanges this service uses. These link to existing pending IDs; this record neither creates nor closes decisions.

Before IaC consumes this contract, provide:

1. A versioned contract revision with actual image source commit/digest, runtime versions, required execution/configuration/access inputs and explicit backend/IaC responsibilities for the deployment increment.
2. Traceable decisions/evidence for each required unknown or accepted proposal, including relevant event/REST/workflow contracts, credentials/secret handling and data/migration compatibility. Resolve or explicitly accept the source-provenance limitations affecting that increment; absent fields are not defaults.
3. Identifiable approval by the authority recorded in the committed pending-decision register: CODEOWNERS **Jhon Galvez and Ramiro Guzman** for backend–IaC coordination and applicable contracts. The rule for one versus both approvals and GitHub handles/enforcement is unknown; do not invent CODEOWNERS configuration. Reference the committed source revision and provide identifiable approval evidence for this delivery contract; source availability alone does not approve it.
4. The applicable independent environment promotion approvals and separate authorization for any infrastructure action. Contract approval alone does not authorize deployment.

**Approval evidence today: none for this service's delivery contract.** ADRs retain their recorded Accepted status; missing individual acceptance records remain PD-014. This document is sufficient to expose gaps while repository initialization proceeds; it is insufficient to claim deployability.
