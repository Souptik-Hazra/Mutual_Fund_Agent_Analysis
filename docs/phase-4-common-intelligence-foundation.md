# Phase 4 — Common Intelligence Foundation

## Objective

Create one canonical identity and provenance layer shared by fund, portfolio, market, news, social, and document intelligence. This phase deliberately precedes autonomous agents: downstream services must agree on what an entity is, where a fact came from, when it was valid, and how confidently a source-to-entity relationship was established.

## Delivered components

- Canonical entity registry for AMCs, schemes, companies, securities, sectors, benchmarks, indices, people, events, regulators, and other reference objects.
- Source-aware aliases with effective date ranges. Duplicate aliases across entities remain ambiguous rather than being silently collapsed.
- Namespaced identifiers such as AMFI scheme codes, ISINs, NSE symbols, and BSE codes. A namespace/value pair cannot be assigned to two entities.
- Source registry with source type, authority tier (1 is highest), official status, base URL, attribution requirement, enabled state, and metadata. AMFI, MFAPI, Nifty Indices, SEBI, NSE, BSE, RBI, and MOSPI are seeded. Reddit and X are registered but disabled until access, terms, and retention are configured.
- Evidence records with external ID, canonical URL, title, publication/retrieval times, effective date range, content hash, verification status, confidence, and metadata.
- Entity-evidence links with relation type, confidence, resolution method, and verification timestamp.
- Typed entity-to-entity relationships with validity dates, source/evidence references, confidence, verification state, and metadata; for example, a scheme can be related to its AMC with a managed_by edge.
- Deterministic resolver: exact identifier first, then exact alias; temporal validity and optional source scope are honored; ambiguous aliases return candidates and are never auto-selected.
- NAV and benchmark ingestion creates or updates canonical entities and stable identifiers; NAV ingestion also registers AMC entities and an explicitly unverified managed_by relationship from provider fund-house metadata.
- Each new NAV and benchmark sync run is hashed, recorded as evidence metadata, and linked to its canonical scheme or benchmark entity. The original raw provider response remains in the existing append-only sync audit table; evidence records do not duplicate full provider payloads.
- Migration backfills identities for already-ingested schemes, AMCs, and benchmarks, including unverified scheme-to-AMC relationships.
- REST API for source listing, entity creation/search/read, alias and identifier registration/listing, evidence creation, entity-evidence linking, paginated evidence listing, relationship management, and identity resolution.

## API

All endpoints are under /api/v1/intelligence.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /sources | List registered sources and authority metadata |
| POST | /entities | Create or retrieve a canonical entity |
| GET | /entities?entity_type=scheme&q=HDFC&limit=50&offset=0 | Search and list canonical entities |
| GET | /entities/{entity_id} | Read one entity |
| POST | /entities/{entity_id}/aliases | Add or update a temporal alias |
| GET | /entities/{entity_id}/aliases | List aliases for an entity |
| POST | /entities/{entity_id}/identifiers | Register a namespaced identifier |
| GET | /entities/{entity_id}/identifiers | List identifiers for an entity |
| POST | /evidence | Create/update a source evidence reference |
| POST | /entities/{entity_id}/evidence/{evidence_id} | Link evidence to an entity |
| GET | /entities/{entity_id}/evidence?limit=50&offset=0 | List evidence linked to an entity (bounded pagination) |
| POST | /entities/{entity_id}/relationships | Create or update a typed temporal relationship |
| GET | /entities/{entity_id}/relationships | List relationships where the entity is either endpoint |
| POST | /resolve | Resolve by exact identifier and/or exact alias |

## Important invariants

1. A canonical entity is unique by entity type and normalized name.
2. A namespaced identifier is unique by namespace and normalized value; at most one primary identifier is allowed per entity and namespace.
3. Alias collisions across entities are legal and reported as ambiguous; each entity can have at most one primary alias.
4. Resolution is deterministic and exact; no fuzzy or LLM identity matching is performed.
5. Identifier and alias validity intervals are inclusive and evaluated against as_of.
6. Source authority is metadata, not a substitute for evidence verification.
7. Social sources are disabled by default; registration does not imply permission to collect or retain content.
8. Evidence stores source references and metadata, not unrestricted copies of copyrighted articles or platform content.
9. Services do not commit transactions; API boundaries own commits and rollbacks.
10. Existing NAV and benchmark schemas remain unchanged; provider sync audit remains the raw-response lineage while evidence records link sync-run IDs and content hashes to canonical entities.

## Validation

Unit tests cover normalization, idempotent entity creation, identifier-first resolution, source-aware and ambiguous aliases, temporal validity, identifier uniqueness, evidence idempotency/linking, relationship validation/idempotency, invalid URLs/confidence, and disabled sources. API contract tests cover route registration, request validation, and bounded pagination.

Run:

    ruff check .
    ruff format --check .
    pytest
    alembic upgrade head

## Deliberate follow-up

- Add reviewed historical validity intervals and conflict-resolution workflow for provider-reported AMC changes.
- Add audited entity merge/reconciliation workflow before automatic fuzzy matching.
- Add source-specific retention enforcement and rights-aware ingestion policies before enabling social connectors.
