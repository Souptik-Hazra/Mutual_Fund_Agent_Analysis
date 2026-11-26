Security identity mapping for market quotes

Twelve Data quote ingestion is fail-closed. A provider quote is persisted only when both the returned ticker and exchange exactly match the request and the request resolves to one active canonical company/security entity.

## Required identifier registry entries

For an NSE security, register these effective-dated rows in entity_identifiers against the same active research_entities.entity_id:

- namespace = ISIN; normalized_value = the exact 12-character Indian ISIN.
- namespace = NSE_SYMBOL; normalized_value = the exact NSE ticker.

For BSE, use BSE_SYMBOL instead. The identifier's source_key must reference an enabled data_sources row with source_type=official and is_official=true. valid_from and valid_to must cover the provider observation's date in Asia/Kolkata.

The canonical research entity must have entity_type company or security and status active. Both identifier mappings must resolve uniquely to that same entity. Do not create these entries from fuzzy name matching or from the Twelve Data response itself; source them from an authoritative exchange/issuer identifier record.

## Quote request contract

- security_key must exactly equal the supplied ISIN or exchange symbol.
- ISIN is mandatory; exchange is exactly NSE or BSE.
- The Twelve Data response must include symbol and exchange, and both must exactly match the requested values.
- The persisted security_key and ISIN are canonicalized to the ISIN; security_name comes from the canonical ResearchEntity.
- Missing, ambiguous, stale or unofficial identifier mappings are rejected. There is no fuzzy fallback.

Twelve Data remains a provider source, not an official source. Its exchange entitlement and personal-use rights must still be confirmed independently before ingestion is enabled.
