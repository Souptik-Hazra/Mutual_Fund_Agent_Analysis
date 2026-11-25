"""Add canonical entities, source registry, and evidence provenance.

Revision ID: 0006_common_intelligence_foundation
Revises: 0005_benchmark_tri
Create Date: 2026-11-25
"""

from alembic import op
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_common_intelligence_foundation"
down_revision = "0005_benchmark_tri"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        Column("source_key", String(60), primary_key=True),
        Column("display_name", String(160), nullable=False),
        Column("source_type", String(20), nullable=False),
        Column("authority_tier", Integer(), nullable=False),
        Column("is_official", Boolean(), nullable=False, server_default="false"),
        Column("base_url", String(500)),
        Column("terms_url", String(500)),
        Column("attribution_required", Boolean(), nullable=False, server_default="false"),
        Column("enabled", Boolean(), nullable=False, server_default="true"),
        Column("metadata", JSONB(), nullable=False, server_default="{}"),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint("authority_tier BETWEEN 1 AND 5", name="ck_data_sources_authority_tier"),
        CheckConstraint(
            "source_type IN ('official', 'provider', 'media', 'social', 'document', 'internal')",
            name="ck_data_sources_source_type",
        ),
    )
    op.create_table(
        "research_entities",
        Column("entity_id", BigInteger(), Identity(), primary_key=True),
        Column("entity_type", String(30), nullable=False),
        Column("canonical_name", String(300), nullable=False),
        Column("normalized_name", String(300), nullable=False),
        Column("description", Text()),
        Column("status", String(20), nullable=False, server_default="active"),
        Column(
            "merged_into_entity_id",
            BigInteger(),
            ForeignKey("research_entities.entity_id", ondelete="RESTRICT"),
        ),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint(
            "entity_type IN ('amc', 'scheme', 'company', 'security', 'sector', "
            "'benchmark', 'index', 'person', 'event', 'regulator', 'other')",
            name="ck_research_entities_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'merged')", name="ck_research_entities_status"
        ),
        UniqueConstraint("entity_type", "normalized_name", name="uq_entity_type_normalized_name"),
    )
    op.create_index(
        "ix_research_entities_type_status", "research_entities", ["entity_type", "status"]
    )
    op.create_table(
        "entity_aliases",
        Column("alias_id", BigInteger(), Identity(), primary_key=True),
        Column(
            "entity_id",
            BigInteger(),
            ForeignKey("research_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("alias", String(300), nullable=False),
        Column("normalized_alias", String(300), nullable=False),
        Column("alias_type", String(30), nullable=False, server_default="common"),
        Column(
            "source_key",
            String(60),
            ForeignKey("data_sources.source_key", ondelete="RESTRICT"),
        ),
        Column("valid_from", Date()),
        Column("valid_to", Date()),
        Column("is_primary", Boolean(), nullable=False, server_default="false"),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_aliases_valid_range",
        ),
        UniqueConstraint(
            "entity_id", "normalized_alias", "valid_from", name="uq_entity_alias_identity"
        ),
    )
    op.create_index("ix_entity_aliases_normalized", "entity_aliases", ["normalized_alias"])
    op.create_table(
        "entity_identifiers",
        Column("identifier_id", BigInteger(), Identity(), primary_key=True),
        Column("entity_id", BigInteger(), ForeignKey(
            "research_entities.entity_id", ondelete="CASCADE"
        ), nullable=False),
        Column("namespace", String(60), nullable=False),
        Column("identifier_value", String(160), nullable=False),
        Column("normalized_value", String(160), nullable=False),
        Column(
            "source_key", String(60),
            ForeignKey("data_sources.source_key", ondelete="RESTRICT"),
        ),
        Column("valid_from", Date()),
        Column("valid_to", Date()),
        Column("is_primary", Boolean(), nullable=False, server_default="false"),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_identifiers_valid_range",
        ),
        UniqueConstraint("namespace", "normalized_value", name="uq_entity_identifier_value"),
    )
    op.create_index("ix_entity_identifiers_entity", "entity_identifiers", ["entity_id"])
    op.create_table(
        "evidence_records",
        Column("evidence_id", BigInteger(), Identity(), primary_key=True),
        Column(
            "source_key",
            String(60),
            ForeignKey("data_sources.source_key", ondelete="RESTRICT"),
            nullable=False,
        ),
        Column("external_id", String(200)),
        Column("canonical_url", String(1000)),
        Column("title", String(500)),
        Column("published_at", DateTime(timezone=True)),
        Column("retrieved_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("effective_from", Date()),
        Column("effective_to", Date()),
        Column("content_hash", String(128)),
        Column("verification_status", String(20), nullable=False, server_default="unverified"),
        Column("confidence", Numeric(4, 3)),
        Column("metadata", JSONB(), nullable=False, server_default="{}"),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint(
            "verification_status IN ('unverified', 'corroborated', 'verified', "
            "'disputed', 'retracted')",
            name="ck_evidence_records_verification_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_evidence_records_confidence",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_evidence_records_effective_range",
        ),
        UniqueConstraint("source_key", "external_id", name="uq_evidence_source_external_id"),
    )
    op.create_index(
        "ix_evidence_source_published", "evidence_records", ["source_key", "published_at"]
    )
    op.create_index("ix_evidence_content_hash", "evidence_records", ["content_hash"])
    op.create_table(
        "entity_evidence_links",
        Column(
            "entity_id",
            BigInteger(),
            ForeignKey("research_entities.entity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column(
            "evidence_id",
            BigInteger(),
            ForeignKey("evidence_records.evidence_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("relation_type", String(40), nullable=False, server_default="mentions"),
        Column("confidence", Numeric(4, 3)),
        Column("resolution_method", String(20), nullable=False, server_default="manual"),
        Column("verified_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_entity_evidence_links_confidence",
        ),
        CheckConstraint(
            "resolution_method IN ('identifier', 'exact_alias', 'manual', 'model_reviewed')",
            name="ck_entity_evidence_links_resolution_method",
        ),
    )
    op.create_index("ix_entity_evidence_links_evidence", "entity_evidence_links", ["evidence_id"])
    op.create_table(
        "entity_relationships",
        Column("relationship_id", BigInteger(), Identity(), primary_key=True),
        Column(
            "from_entity_id",
            BigInteger(),
            ForeignKey("research_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column(
            "to_entity_id",
            BigInteger(),
            ForeignKey("research_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("relation_type", String(50), nullable=False),
        Column(
            "source_key", String(60),
            ForeignKey("data_sources.source_key", ondelete="RESTRICT"),
        ),
        Column(
            "evidence_id",
            BigInteger(),
            ForeignKey("evidence_records.evidence_id", ondelete="RESTRICT"),
        ),
        Column("valid_from", Date()),
        Column("valid_to", Date()),
        Column("confidence", Numeric(4, 3)),
        Column("verification_status", String(20), nullable=False, server_default="unverified"),
        Column("metadata", JSONB(), nullable=False, server_default="{}"),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        CheckConstraint("from_entity_id <> to_entity_id", name="ck_entity_relationships_not_self"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_relationships_valid_range",
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'corroborated', 'verified', "
            "'disputed', 'retracted')",
            name="ck_entity_relationships_verification_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_entity_relationships_confidence",
        ),
        UniqueConstraint(
            "from_entity_id",
            "to_entity_id",
            "relation_type",
            "valid_from",
            name="uq_entity_relationship_identity",
        ),
    )
    op.create_index(
        "ix_entity_relationships_from",
        "entity_relationships",
        ["from_entity_id", "relation_type"],
    )
    op.create_index(
        "ix_entity_relationships_to",
        "entity_relationships",
        ["to_entity_id", "relation_type"],
    )

    source_table = Table(
        "data_sources",
        MetaData(),
        Column("source_key", String(60)),
        Column("display_name", String(160)),
        Column("source_type", String(20)),
        Column("authority_tier", Integer()),
        Column("is_official", Boolean()),
        Column("base_url", String(500)),
        Column("attribution_required", Boolean()),
        Column("enabled", Boolean()),
        Column("metadata", JSONB()),
    )
    op.bulk_insert(source_table, [
        {"source_key": "amfi", "display_name": "Association of Mutual Funds in India",
         "source_type": "official", "authority_tier": 1, "is_official": True,
         "base_url": "https://www.amfiindia.com/", "attribution_required": False,
         "enabled": True, "metadata": {"domain": "mutual_fund_nav", "role": "primary_disclosure"}},
        {"source_key": "mfapi", "display_name": "MFAPI", "source_type": "provider",
         "authority_tier": 2, "is_official": False, "base_url": "https://api.mfapi.in/",
         "attribution_required": False, "enabled": True,
         "metadata": {"domain": "mutual_fund_nav", "role": "aggregated_provider"}},
        {"source_key": "niftyindices", "display_name": "Nifty Indices", "source_type": "official",
         "authority_tier": 1, "is_official": True, "base_url": "https://www.niftyindices.com/",
         "attribution_required": False, "enabled": True,
         "metadata": {"domain": "benchmark", "role": "index_publisher"}},
        {"source_key": "sebi", "display_name": "Securities and Exchange Board of India",
         "source_type": "official", "authority_tier": 1, "is_official": True,
         "base_url": "https://www.sebi.gov.in/", "attribution_required": False, "enabled": True,
         "metadata": {"domain": "regulatory", "role": "regulator"}},
        {"source_key": "nse", "display_name": "National Stock Exchange of India",
         "source_type": "official", "authority_tier": 1, "is_official": True,
         "base_url": "https://www.nseindia.com/", "attribution_required": False, "enabled": True,
         "metadata": {"domain": "exchange", "role": "exchange_disclosure"}},
        {"source_key": "bse", "display_name": "BSE Limited", "source_type": "official",
         "authority_tier": 1, "is_official": True, "base_url": "https://www.bseindia.com/",
         "attribution_required": False, "enabled": True,
         "metadata": {"domain": "exchange", "role": "exchange_disclosure"}},
        {"source_key": "rbi", "display_name": "Reserve Bank of India", "source_type": "official",
         "authority_tier": 1, "is_official": True, "base_url": "https://www.rbi.org.in/",
         "attribution_required": False, "enabled": True,
         "metadata": {"domain": "macro", "role": "central_bank"}},
        {
            "source_key": "mospi",
            "display_name": "Ministry of Statistics and Programme Implementation",
         "source_type": "official", "authority_tier": 1, "is_official": True,
         "base_url": "https://www.mospi.gov.in/", "attribution_required": False, "enabled": True,
         "metadata": {"domain": "macro", "role": "statistics_publisher"}},
        {"source_key": "reddit", "display_name": "Reddit", "source_type": "social",
         "authority_tier": 4, "is_official": False, "base_url": "https://www.reddit.com/",
         "attribution_required": True, "enabled": False,
         "metadata": {"domain": "social", "role": "public_discussion"}},
        {"source_key": "x", "display_name": "X", "source_type": "social",
         "authority_tier": 4, "is_official": False, "base_url": "https://x.com/",
         "attribution_required": True, "enabled": False,
         "metadata": {"domain": "social", "role": "public_discussion"}},
    ])

    # Backfill stable identities for the already-ingested scheme and benchmark catalogues.
    op.execute("""
        INSERT INTO research_entities (
            entity_type, canonical_name, normalized_name, status
        )
        SELECT
            'scheme',
            scheme_name || ' [' || scheme_code::text || ']',
            lower(regexp_replace(btrim(scheme_name || ' [' || scheme_code::text || ']'),
                                 '\\s+', ' ', 'g')),
            'active'
        FROM mutual_fund_schemes
        ON CONFLICT (entity_type, normalized_name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO entity_aliases (
            entity_id, alias, normalized_alias, alias_type, source_key, is_primary
        )
        SELECT e.entity_id, s.scheme_name,
               lower(regexp_replace(btrim(s.scheme_name), '\\s+', ' ', 'g')),
               'provider_name', s.source, true
        FROM mutual_fund_schemes s
        JOIN research_entities e
          ON e.entity_type = 'scheme'
         AND e.normalized_name = lower(regexp_replace(
             btrim(s.scheme_name || ' [' || s.scheme_code::text || ']'), '\\s+', ' ', 'g'
         ))
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO entity_identifiers (
            entity_id, namespace, identifier_value, normalized_value, source_key, is_primary
        )
        SELECT e.entity_id, 'AMFI_SCHEME_CODE', s.scheme_code::text,
               s.scheme_code::text, 'amfi', true
        FROM mutual_fund_schemes s
        JOIN research_entities e
          ON e.entity_type = 'scheme'
         AND e.normalized_name = lower(regexp_replace(
             btrim(s.scheme_name || ' [' || s.scheme_code::text || ']'), '\\s+', ' ', 'g'
         ))
        ON CONFLICT (namespace, normalized_value) DO NOTHING
    """)
    op.execute("""
        INSERT INTO entity_identifiers (
            entity_id, namespace, identifier_value, normalized_value, source_key, is_primary
        )
        SELECT e.entity_id, 'ISIN', i.isin, upper(btrim(i.isin)), 'amfi', false
        FROM mutual_fund_schemes s
        JOIN research_entities e
          ON e.entity_type = 'scheme'
         AND e.normalized_name = lower(regexp_replace(
             btrim(s.scheme_name || ' [' || s.scheme_code::text || ']'), '\\s+', ' ', 'g'
         ))
        CROSS JOIN LATERAL (
            VALUES (s.isin_growth), (s.isin_div_reinvestment)
        ) AS i(isin)
        WHERE i.isin IS NOT NULL AND btrim(i.isin) <> ''
        ON CONFLICT (namespace, normalized_value) DO NOTHING
    """)
    op.execute("""
        INSERT INTO research_entities (
            entity_type, canonical_name, normalized_name, status
        )
        SELECT 'benchmark', benchmark_name || ' [' || benchmark_code || ']',
               lower(btrim(benchmark_name || ' [' || benchmark_code || ']')), 'active'
        FROM benchmark_indices
        ON CONFLICT (entity_type, normalized_name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO entity_identifiers (
            entity_id, namespace, identifier_value, normalized_value, source_key, is_primary
        )
        SELECT e.entity_id, 'BENCHMARK_CODE', b.benchmark_code,
               upper(btrim(b.benchmark_code)), 'niftyindices', true
        FROM benchmark_indices b
        JOIN research_entities e
          ON e.entity_type = 'benchmark'
         AND e.normalized_name = lower(btrim(b.benchmark_name || ' [' || b.benchmark_code || ']'))
        ON CONFLICT (namespace, normalized_value) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_entity_relationships_to", table_name="entity_relationships")
    op.drop_index("ix_entity_relationships_from", table_name="entity_relationships")
    op.drop_table("entity_relationships")
    op.drop_index("ix_entity_evidence_links_evidence", table_name="entity_evidence_links")
    op.drop_table("entity_evidence_links")
    op.drop_index("ix_evidence_content_hash", table_name="evidence_records")
    op.drop_index("ix_evidence_source_published", table_name="evidence_records")
    op.drop_table("evidence_records")
    op.drop_index("ix_entity_identifiers_entity", table_name="entity_identifiers")
    op.drop_table("entity_identifiers")
    op.drop_index("ix_entity_aliases_normalized", table_name="entity_aliases")
    op.drop_table("entity_aliases")
    op.drop_index("ix_research_entities_type_status", table_name="research_entities")
    op.drop_table("research_entities")
    op.drop_table("data_sources")
