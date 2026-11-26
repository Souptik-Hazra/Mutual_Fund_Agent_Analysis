# Focused Security Review

**Review date:** 2026-11-26  
**Scope:** Local-first FastAPI, React/Vite, PostgreSQL, Qdrant, document and financial-research workflows.  
**Assumption:** Personal single-user local application. This is a scoped code/configuration review, not a penetration test or formal security certification.

## Verified controls

| Area | Observed control | Assessment |
|---|---|---|
| Host network exposure | Docker Compose binds API and PostgreSQL to `127.0.0.1`; Qdrant has no published host port and remains on the Compose network. | Verified in `docker-compose.yml`. Preserve these bindings. |
| HTTP logs | Request middleware logs request ID, method, path, status and duration; it does not log query strings, request bodies or headers. | Verified in `main.py`. |
| Research tracing | Assistant requests receive a separate `research_run_id`, returned in stream and non-stream responses, placed in SSE events and propagated through graph state. Specialist logs contain specialist/status and run ID, not portfolio payloads. | Verified in assistant routes and graph code. |
| Dependency scans | CI runs `pip-audit --skip-editable` without suppressing vulnerability IDs and `npm audit --audit-level=high` against the committed lockfile. | Verified in `.github/workflows/ci.yml`. |
| Source URL validation | Provider/feed URLs are checked against HTTPS and registered host rules before collection. | Existing source-registry tests cover invalid hosts and non-HTTPS feeds. |
| Document uploads | PDF uploads are limited to 25 MiB, parsed by the PDF parser and reject malformed/encrypted content. | Existing tests cover size and parse failures. Content-type/extension checks are not a full MIME-signature security boundary. |
| Spreadsheet uploads | CSV/XLSX imports have file-size, row/column and ZIP expansion/compression-ratio limits. | Existing import-boundary tests cover oversized/sparse inputs. |
| Social ingestion | Collection is fail-closed unless source terms URL, terms review and access confirmation metadata are present; retention expiry is applied. | Code controls verified. Human review of current Reddit/X terms and account entitlement is still required. |
| Qdrant | Qdrant is private to the Compose network. Lexical PostgreSQL document retrieval remains available when the semantic index is unavailable. Document deletion requires successful vector cleanup first. | Verified in Compose, service code and lifecycle tests. |
| API errors/secrets | Provider errors are normalized rather than returning raw URLs/keys from upstream failures. | Existing Twelve Data error-redaction tests cover secret leakage. |

## Findings and limitations

### S1 — No user authentication

The local API does not implement production user authentication or multi-user authorization. This is consistent with the personal local-only scope, but the application must not be exposed to a LAN, reverse proxy or public network. Loopback binding is a network restriction, not an authentication system.

### S2 — PDF MIME verification

The upload handler checks the declared content type or `.pdf` filename and then validates the input through the PDF parser. Parser validation and the 25 MiB read limit are important safeguards, but a file signature check is not the same as a complete file-type security validation.

### S3 — Third-party provider governance

Reddit/X and Twelve Data access depends on current terms, credentials and plan entitlements that code and mock tests cannot verify. Keep social collection disabled until a human records current terms/access approval. Keep Twelve Data live validation blocked until a real API key and confirmed exchange entitlement are available.

### S4 — Dependency scanning is not a full security assessment

`pip-audit` and `npm audit` provide dependency vulnerability checks. They do not constitute comprehensive static analysis, secrets scanning, dynamic testing or penetration testing. The application has not been certified for public or multi-user hosting.

## Operational guidance

- Run the application on the local machine only; retain loopback bindings and do not publish Qdrant.
- Keep provider credentials in local environment configuration. Do not commit `.env` files or place secrets in logs.
- Keep Reddit/X disabled until terms and account access have been manually reviewed.
- Treat backup archives as sensitive personal financial data and protect them accordingly.
- Revisit this review if the local-only deployment boundary changes.

## Explicitly not claimed

This review does not claim a penetration test, comprehensive SAST/DAST, legal approval of third-party terms, live provider entitlement validation or readiness for public hosting.