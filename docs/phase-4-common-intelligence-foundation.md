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
- Deterministic resolver: exact identifier first, then exact alias; temporal validity is honored; ambiguous aliases return candidates and are never auto-selected.
- REST API for source listing, entity creation/read, alias and identifier registration, evidence creation, entity-evidence linking, evidence listing, and identity resolution.

## API

All endpoints are under /api/v1/intelligence.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /sources | List registered sources and authority metadata |
| POST | /entities | Create or retrieve a canonical entity |
| GET | /entities/{entity_id} | Read one entity |
| POST | /entities/{entity_id}/aliases | Add or update a temporal alias |
| POST | /entities/{entity_id}/identifiers | Register a namespaced identifier |
| POST | /evidence | Create/update a source evidence reference |
| POST | /entities/{entity_id}/evidence/{evidence_id} | Link evidence to an entity |
| GET | /entities/{entity_id}/evidence | List evidence linked to an entity |
| POST | /resolve | Resolve by exact identifier and/or exact alias |

## Important invariants

1. A canonical entity is unique by entity type and normalized name.
2. A namespaced identifier is unique by namespace and normalized value.
3. Alias collisions across entities are legal and reported as ambiguous.
4. Resolution is deterministic and exact; no fuzzy or LLM identity matching is performed.
5. Identifier and alias validity intervals are inclusive and evaluated against as_of.
6. Source authority is metadata, not a substitute for evidence verification.
7. Social sources are disabled by default; registration does not imply permission to collect or retain content.
8. Evidence stores source references and metadata, not unrestricted copies of copyrighted articles or platform content.
9. Services do not commit transactions; API boundaries own commits and rollbacks.
10. Existing NAV and benchmark schemas remain unchanged; provider sync audit remains their lineage source until ingestion services are migrated to evidence links.

## Validation

Unit tests cover normalization, idempotent entity creation, identifier-first resolution, ambiguous aliases, temporal validity, identifier uniqueness, evidence idempotency/linking, invalid URLs/confidence, and disabled sources. API contract tests cover route registration and request validation.

Run:

    ruff check .
    ruff format --check .
    pytest
    alembic upgrade head

## Deliberate follow-up

- Add verified entity-evidence links to NAV and benchmark sync runs after confirming provider record identity and audit semantics.
- Add evidence links to NAV and benchmark sync runs after validating provider-specific record identity.
- Add audited entity merge/reconciliation workflow before automatic fuzzy matching.
- Add source-specific retention enforcement and rights-aware ingestion policies before enabling social connectors.
