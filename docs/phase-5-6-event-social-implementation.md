# Phase 5 and Phase 6 — Event and Social Intelligence

This document maps to the project's fixed roadmap:
- **Phase 5:** Event and News Intelligence
- **Phase 6:** Social Intelligence

The implementation is local-first. External collection remains opt-in and is blocked until the operator records provider access and terms review. No source access, sentiment accuracy, or official feed availability is assumed.

## Phase 5 — Event and News Intelligence

### Delivered

- Normalized market events retain source, external ID, canonical entity, linked evidence, event type/status, event date, publication timestamp, and confidence.
- RSS/Atom ingestion is limited to enabled, official sources with HTTPS base URLs, an exact registered host, a terms URL, and explicit `terms_reviewed`, `access_confirmed`, and `reviewed_at` source metadata.
- RSS downloads have connect/overall timeouts, a 5 MB streaming response cap, no redirects, a 250-item processing cap, safe HTTPS links, malformed XML handling, and rejection of document-type/entity declarations.
- RSS items are always stored as **reported** with **unverified** evidence. Feed headlines never promote themselves to confirmed/scheduled facts.
- Publication time and effective event date are distinct. An event date is populated only from an explicit feed field; publication date is not silently substituted.
- Repeated source items are idempotently identified. Changed source observations append an immutable event revision and reset changed evidence to unverified.
- Headline-to-company linking uses active, date-valid, source-aware exact aliases only. A link is created only when exactly one company matches. Ambiguous or absent matches remain unlinked; no fuzzy guess is made.
- Existing reviewed/manual entity links are preserved when a feed refresh cannot resolve an entity.
- Manual event creation enforces evidence for confirmed/scheduled/disproved events, and verified/corroborated evidence for confirmed/scheduled events. Reported/unverified/speculative events require a source URL or evidence.
- Fund exposure uses the latest portfolio snapshot effective on or before the event date and explicitly reports when no historical snapshot exists.

### API

- `POST /api/v1/events` — add/update a normalized event.
- `GET /api/v1/events` — filter events by date, status, and entity.
- `POST /api/v1/events/collect/{source_key}?feed_url=...` — collect from an approved registered RSS/Atom source.
- `GET /api/v1/events/{event_id}/revisions` — inspect the event's revision history.
- `GET /api/v1/events/fund-exposure/{scheme_code}` — map events to historically effective fund holdings.

### Operator setup

Register an official source only after independently checking its feed, terms, and access. Set source metadata to include:
```json
{
  "terms_reviewed": true,
  "access_confirmed": true,
  "reviewed_at": "YYYY-MM-DD"
}
```
The registered `base_url` must be HTTPS and its hostname must exactly match the configured feed host. The terms URL and review metadata are mandatory; the code does not claim to have reviewed the source on the user's behalf.

### Deliberate limits

- RSS title classification is deterministic keyword categorization, not semantic verification.
- Entity linking is conservative and alias-based; it does not infer relationships or map an ambiguous headline.
- A publication timestamp is not an event effective date.
- Official exchange/regulator feed URLs and schedules must be supplied and verified by the operator. No live feed is enabled by default.

## Phase 6 — Social Intelligence

### Delivered

- Official Reddit OAuth and X API v2 recent-search clients remain separate provider adapters. Credentials are optional for application startup; `GET /api/v1/social/providers` reports readiness without exposing secret values.
- Collection is blocked unless the source is enabled, classified as social, has a terms URL, and has explicit `terms_reviewed`, `access_confirmed`, and `reviewed_at` metadata.
- Provider authorization failures are returned as access-denied responses; rate limits are surfaced as rate limits rather than generic server errors.
- Persisted social records contain provider IDs, canonical URLs, SHA-256 content hashes, publication time, engagement metadata, optional entity IDs, and expiry. Text excerpts and raw text fields are discarded before persistence.
- Expiry is enforced on write using the source-specific `metadata.retention_days` (1–365) or the configured global `SOCIAL_RETENTION_DAYS` fallback. The API rejects records whose expiry exceeds that policy.
- `mfa-purge-expired-social` deletes expired social rows; schedule it locally at a cadence consistent with the reviewed provider terms.
- Sentiment is not inferred during collection. Label, score, and model identifier must be supplied together. A model identifier is accepted only if it appears in that source's `metadata.evaluated_sentiment_models` allowlist.
- Social analytics disclose source counts and scored/unscored counts, and only aggregate supplied sentiment scores.
- Fund social sentiment is time-weighted against portfolio holdings effective during each post's publication interval and reports coverage. It remains an experimental discussion indicator, not a NAV/return predictor or recommendation.

### API

- `GET /api/v1/social/providers` — reports whether credentials, source enablement, and terms/access review permit collection or manual import.
- `GET /api/v1/social/collect?source=reddit|x&q=...` — opt-in provider collection; returns HTTP 409 with an actionable explanation when credentials are absent.
- `POST /api/v1/social/import-file` — import up to 500 authorized records from CSV or JSON (maximum 5 MB) when the matching source has been enabled and reviewed.
- `POST /api/v1/social/posts` — ingest normalized post metadata and optional approved external sentiment.
- `GET /api/v1/social/analytics` — discussion volume and scored sentiment coverage.
- `GET /api/v1/social/funds/{scheme_code}/sentiment?start_date=...&end_date=...` — holdings-weighted company discussion signal.

### Operator setup

For each provider, review the current API tier, access, terms, attribution, and deletion obligations. Configure a source with:
- `source_type="social"`, `enabled=true` only after review.
- A provider-specific terms URL.
- `metadata.terms_reviewed=true`, `metadata.access_confirmed=true`, and `metadata.reviewed_at="YYYY-MM-DD"`.
- `metadata.retention_days` set to the reviewed retention period (1–365).
- `metadata.evaluated_sentiment_models` containing only finance sentiment model IDs that have been independently evaluated. Leave it empty when no such model is approved.

Credentials are supplied through `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, and `X_BEARER_TOKEN`; they are optional and empty values are treated as unconfigured. When API access is unavailable, an operator may import a CSV/JSON export only when the source is enabled and its terms/access review is recorded. Supported import fields include `external_id`, `text_excerpt` (or `text`), `canonical_url` (or `url`), `published_at`, `engagement_count`, `related_entity_id`, `metadata`, and optional evaluated sentiment fields. Imports receive a SHA-256 hash and source-specific expiry; raw text is discarded by the persistence service. Provider credentials do not bypass the source review gate.

### Deliberate limits

- Reddit/X sources remain disabled until the operator verifies current access and terms. This implementation does not claim the user's account has API access.
- Missing API keys do not disable the rest of the application. News/event data remains a separate source category and must not be reported as Reddit/X community sentiment. Manual import is not a workaround for platform terms or export restrictions.
- Collected posts are not automatically assigned to a company; supply a canonical `related_entity_id` after deterministic resolution.
- Sentiment requires a separately evaluated finance model. No keyword sentiment heuristic is used.
- Engagement and discussion volume are not credibility, causal impact, or NAV predictors.
- Expiry purge is a local scheduled operation; run `mfa-purge-expired-social` daily or more frequently if provider terms require it.
