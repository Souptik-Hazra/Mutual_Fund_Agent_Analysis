"""Deterministic portfolio, event, social, and document intelligence services."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models import (
    DataSource, DocumentChunk, EvidenceRecord, MarketEvent, MutualFundScheme,
    PortfolioHolding, PortfolioSnapshot, ResearchDocument, ResearchEntity, SocialPost,
)

D = Decimal


def import_portfolio_snapshot(session: Session, payload: Any) -> PortfolioSnapshot:
    """Idempotently persist one disclosure version and its normalized positions."""
    if session.get(MutualFundScheme, payload.scheme_code) is None:
        raise ValueError("Unknown scheme_code; ingest the scheme catalogue first.")
    source = session.get(DataSource, payload.source_key)
    if source is None or not source.enabled:
        raise ValueError("Unknown or disabled source_key.")
    existing = session.scalar(select(PortfolioSnapshot).where(
        PortfolioSnapshot.scheme_code == payload.scheme_code,
        PortfolioSnapshot.effective_date == payload.effective_date,
        PortfolioSnapshot.source_key == payload.source_key,
        PortfolioSnapshot.content_hash == payload.content_hash,
    ))
    if existing:
        return existing
    evidence_external_id = (
        f"portfolio:{payload.scheme_code}:{payload.effective_date}:{payload.content_hash}"
    )
    evidence = session.scalar(select(EvidenceRecord).where(
        EvidenceRecord.source_key == payload.source_key,
        EvidenceRecord.external_id == evidence_external_id,
    ))
    if evidence is None:
        evidence = EvidenceRecord(
            source_key=payload.source_key, external_id=evidence_external_id,
            canonical_url=str(payload.document_url) if payload.document_url else None,
            title=f"Portfolio disclosure for scheme {payload.scheme_code}",
            published_at=payload.published_at, effective_from=payload.effective_date,
            content_hash=payload.content_hash, verification_status="unverified",
            metadata_json={"scheme_code": payload.scheme_code, "ingestion": "portfolio_snapshot"},
        )
        session.add(evidence)
        session.flush()
    snapshot = PortfolioSnapshot(
        scheme_code=payload.scheme_code, source_key=payload.source_key,
        evidence_id=evidence.evidence_id, effective_date=payload.effective_date,
        published_at=payload.published_at,
        document_url=str(payload.document_url) if payload.document_url else None,
        content_hash=payload.content_hash, total_market_value=payload.total_market_value,
        status=payload.status, metadata_json=payload.metadata,
    )
    session.add(snapshot)
    session.flush()
    from mutual_fund_agent_analysis.models import EntityIdentifier
    for item in payload.holdings:
        company_entity_id = None
        if item.isin:
            company_entity_id = session.scalar(
                select(EntityIdentifier.entity_id)
                .join(ResearchEntity, ResearchEntity.entity_id == EntityIdentifier.entity_id)
                .where(EntityIdentifier.namespace == "ISIN")
                .where(EntityIdentifier.normalized_value == item.isin.strip().upper())
                .where(ResearchEntity.entity_type.in_([ "company", "security" ]))
                .limit(1)
            )
        session.add(PortfolioHolding(
            snapshot_id=snapshot.snapshot_id, security_key=item.security_key.strip().upper(),
            isin=item.isin.strip().upper() if item.isin else None,
            security_name=item.security_name.strip(), company_entity_id=company_entity_id,
            sector=item.sector,
            asset_class=item.asset_class, quantity=item.quantity, market_value=item.market_value,
            weight_pct=item.weight_pct, currency=item.currency.upper(), metadata_json=item.metadata,
        ))
    session.commit()
    session.refresh(snapshot)
    return snapshot


def latest_snapshot(session: Session, scheme_code: int, as_of: date | None = None) -> PortfolioSnapshot | None:
    stmt = select(PortfolioSnapshot).where(PortfolioSnapshot.scheme_code == scheme_code)
    if as_of:
        stmt = stmt.where(PortfolioSnapshot.effective_date <= as_of)
    return session.scalar(stmt.order_by(PortfolioSnapshot.effective_date.desc(), PortfolioSnapshot.snapshot_id.desc()).limit(1))


def portfolio_payload(session: Session, snapshot: PortfolioSnapshot) -> dict[str, Any]:
    rows = session.scalars(select(PortfolioHolding).where(
        PortfolioHolding.snapshot_id == snapshot.snapshot_id
    ).order_by(PortfolioHolding.weight_pct.desc().nullslast(), PortfolioHolding.security_name)).all()
    known = [r for r in rows if r.weight_pct is not None]
    weights = [r.weight_pct / D("100") for r in known]
    weight_coverage = sum((r.weight_pct for r in known), D("0"))
    hhi = (
        sum((w * w for w in weights), D("0"))
        if weights and D("99") <= weight_coverage <= D("101")
        else None
    )
    sectors: dict[str, Decimal] = defaultdict(lambda: D("0"))
    assets: dict[str, Decimal] = defaultdict(lambda: D("0"))
    for row in rows:
        if row.weight_pct is not None:
            assets[row.asset_class] += row.weight_pct
            sectors[row.sector or "Unclassified"] += row.weight_pct
    return {
        "snapshot_id": snapshot.snapshot_id, "scheme_code": snapshot.scheme_code,
        "source_key": snapshot.source_key, "effective_date": snapshot.effective_date,
        "published_at": snapshot.published_at, "status": snapshot.status,
        "content_hash": snapshot.content_hash, "total_market_value": snapshot.total_market_value,
        "holdings_count": len(rows), "holdings": [{
            "security_key": r.security_key, "isin": r.isin, "security_name": r.security_name,
            "sector": r.sector, "asset_class": r.asset_class, "quantity": r.quantity,
            "market_value": r.market_value, "weight_pct": r.weight_pct, "currency": r.currency,
        } for r in rows],
        "top_5": [{"security_key": r.security_key, "name": r.security_name, "weight_pct": r.weight_pct} for r in known[:5]],
        "top_10": [{"security_key": r.security_key, "name": r.security_name, "weight_pct": r.weight_pct} for r in known[:10]],
        "top_20": [{"security_key": r.security_key, "name": r.security_name, "weight_pct": r.weight_pct} for r in known[:20]],
        "sector_allocation": [{"sector": k, "weight_pct": v} for k, v in sorted(sectors.items(), key=lambda x: x[1], reverse=True)],
        "asset_allocation": [{"asset_class": k, "weight_pct": v} for k, v in sorted(assets.items(), key=lambda x: x[1], reverse=True)],
        "hhi_0_to_1": hhi,
        "weight_coverage_pct": weight_coverage,
        "hhi_coverage_sufficient": hhi is not None,
        "disclosure_url": snapshot.document_url,
    }


def portfolio_history(session: Session, scheme_code: int) -> list[dict[str, Any]]:
    rows = session.scalars(select(PortfolioSnapshot).where(
        PortfolioSnapshot.scheme_code == scheme_code
    ).order_by(PortfolioSnapshot.effective_date.desc())).all()
    result = []
    for snap in rows:
        holdings = session.scalars(select(PortfolioHolding).where(
            PortfolioHolding.snapshot_id == snap.snapshot_id
        )).all()
        sectors: dict[str, Decimal] = defaultdict(lambda: D("0"))
        for holding in holdings:
            if holding.weight_pct is not None:
                sectors[holding.sector or "Unclassified"] += holding.weight_pct
        result.append({
            "snapshot_id": snap.snapshot_id, "effective_date": snap.effective_date,
            "published_at": snap.published_at, "source_key": snap.source_key,
            "status": snap.status, "holding_count": len(holdings),
            "weight_coverage_pct": sum((h.weight_pct or D("0") for h in holdings), D("0")),
            "sector_allocation": [{"sector": key, "weight_pct": value}
                                  for key, value in sorted(sectors.items(), key=lambda item: item[1], reverse=True)],
        })
    return result


def compare_portfolios(
    session: Session, scheme_codes: list[int], as_of: date | None = None
) -> dict[str, Any]:
    snapshots = {code: latest_snapshot(session, code, as_of) for code in scheme_codes}
    if any(value is None for value in snapshots.values()):
        missing = [code for code, value in snapshots.items() if value is None]
        raise ValueError(f"No portfolio disclosure available for scheme(s): {missing}")
    maps: dict[int, dict[str, Decimal]] = {}
    names: dict[str, str] = {}
    for code, snap in snapshots.items():
        rows = session.scalars(select(PortfolioHolding).where(
            PortfolioHolding.snapshot_id == snap.snapshot_id
        )).all()
        maps[code] = {}
        for row in rows:
            if row.weight_pct is not None:
                maps[code][row.security_key] = row.weight_pct
                names[row.security_key] = row.security_name
    pairwise = []
    for i, left in enumerate(scheme_codes):
        for right in scheme_codes[i + 1:]:
            common = set(maps[left]) & set(maps[right])
            overlap = sum((min(maps[left][key], maps[right][key]) for key in common), D("0"))
            pairwise.append({
                "scheme_a": left, "scheme_b": right, "common_holding_count": len(common),
                "overlap_pct": overlap, "common_securities": [
                    {"security_key": key, "name": names[key], "weight_a": maps[left][key],
                     "weight_b": maps[right][key]} for key in sorted(common)
                ],
            })
    return {
        "as_of": {str(code): snapshots[code].effective_date for code in scheme_codes},
        "pairwise_overlap": pairwise,
    }


def security_fund_exposure(session: Session, security_key: str) -> dict[str, Any]:
    key = security_key.strip().upper()
    ranked_snapshots = select(
        PortfolioSnapshot.snapshot_id,
        func.row_number().over(
            partition_by=PortfolioSnapshot.scheme_code,
            order_by=(PortfolioSnapshot.effective_date.desc(), PortfolioSnapshot.snapshot_id.desc()),
        ).label("snapshot_rank"),
    ).subquery()
    stmt = (
        select(PortfolioHolding, PortfolioSnapshot, MutualFundScheme)
        .join(PortfolioSnapshot, PortfolioSnapshot.snapshot_id == PortfolioHolding.snapshot_id)
        .join(MutualFundScheme, MutualFundScheme.scheme_code == PortfolioSnapshot.scheme_code)
        .join(ranked_snapshots, ranked_snapshots.c.snapshot_id == PortfolioSnapshot.snapshot_id)
        .where(ranked_snapshots.c.snapshot_rank == 1)
        .where(PortfolioHolding.security_key == key)
        .order_by(PortfolioHolding.weight_pct.desc().nullslast())
    )
    rows = session.execute(stmt).all()
    funds = [{
        "scheme_code": h.scheme_code, "scheme_name": s.scheme_name,
        "effective_date": p.effective_date, "weight_pct": h.weight_pct,
        "market_value": h.market_value, "source_key": p.source_key,
    } for h, p, s in rows]
    return {"security_key": key, "funds": funds, "total_fund_count": len(funds)}


def collect_rss_events(session: Session, source_key: str, feed_url: str) -> dict[str, Any]:
    """Ingest RSS/Atom items as reported (never confirmed) events with evidence records."""
    from urllib.parse import urlparse
    from mutual_fund_agent_analysis.data.providers.rss import fetch_feed

    source = session.get(DataSource, source_key)
    if source is None or not source.enabled or not source.base_url:
        raise ValueError("Source must be registered, enabled, and have an official base_url.")
    allowed_host = urlparse(source.base_url).hostname
    if not allowed_host:
        raise ValueError("Registered source base_url is invalid.")
    items = fetch_feed(feed_url, allowed_host)
    created = updated = 0
    for item in items:
        external_id = "rss:" + item["external_id"]
        evidence = session.scalar(select(EvidenceRecord).where(
            EvidenceRecord.source_key == source_key, EvidenceRecord.external_id == external_id
        ))
        digest = hashlib.sha256((item["title"] + item["summary"]).encode("utf-8")).hexdigest()
        if evidence is None:
            evidence = EvidenceRecord(
                source_key=source_key, external_id=external_id, canonical_url=item["url"],
                title=item["title"], published_at=item["published_at"],
                content_hash=digest, verification_status="unverified",
                metadata_json={"ingestion": "rss_atom", "feed_url": feed_url},
            )
            session.add(evidence)
            session.flush()
        else:
            evidence.title = item["title"]
            evidence.canonical_url = item["url"]
            evidence.published_at = item["published_at"]
            if evidence.content_hash != digest:
                evidence.verification_status = "unverified"
            evidence.content_hash = digest
        event = session.scalar(select(MarketEvent).where(
            MarketEvent.source_key == source_key, MarketEvent.external_id == external_id
        ))
        event_type = "other"
        title_lower = item["title"].lower()
        for term, category in (
            ("board meeting", "board_meeting"), ("financial results", "results"),
            ("quarterly results", "results"), ("dividend", "dividend"),
            ("record date", "record_date"), ("stock split", "split"),
            ("bonus issue", "bonus"), ("merger", "merger"),
            ("acquisition", "acquisition"), ("fund raising", "fundraising"),
            ("management", "management"), ("circular", "regulatory"),
        ):
            if term in title_lower:
                event_type = category
                break
        values = {
            "evidence_id": evidence.evidence_id, "title": item["title"],
            "summary": item["summary"], "event_type": event_type, "status": "reported",
            "event_date": item["published_at"].date() if item["published_at"] else None,
            "published_at": item["published_at"], "canonical_url": item["url"],
            "metadata_json": {"ingestion": "rss_atom", "feed_url": feed_url},
        }
        if event is None:
            session.add(MarketEvent(source_key=source_key, external_id=external_id, **values))
            created += 1
        else:
            for key, value in values.items():
                setattr(event, key, value)
            updated += 1
    session.commit()
    return {"source_key": source_key, "feed_url": feed_url, "fetched": len(items),
            "created": created, "updated": updated,
            "status_policy": "RSS items are stored as reported, never automatically confirmed."}


def create_market_event(session: Session, payload: Any) -> MarketEvent:
    source = session.get(DataSource, payload.source_key)
    if source is None or not source.enabled:
        raise ValueError("Unknown or disabled source_key.")
    if payload.related_entity_id and session.get(ResearchEntity, payload.related_entity_id) is None:
        raise ValueError("Unknown related_entity_id.")
    evidence = session.get(EvidenceRecord, payload.evidence_id) if payload.evidence_id else None
    if payload.evidence_id and evidence is None:
        raise ValueError("Unknown evidence_id.")
    if payload.status in {"confirmed", "scheduled", "disproved"} and evidence is None:
        raise ValueError("Confirmed, scheduled, and disproved events require a linked evidence record.")
    if payload.status in {"confirmed", "scheduled"} and (
        evidence is None or evidence.verification_status not in {"verified", "corroborated"}
    ):
        raise ValueError("Confirmed or scheduled events require verified or corroborated evidence.")
    if payload.status == "scheduled" and not source.is_official:
        raise ValueError("Scheduled events must originate from an official source.")
    event = MarketEvent(
        source_key=payload.source_key, external_id=payload.external_id,
        related_entity_id=payload.related_entity_id, evidence_id=payload.evidence_id,
        title=payload.title, summary=payload.summary, event_type=payload.event_type,
        status=payload.status, event_date=payload.event_date, published_at=payload.published_at,
        canonical_url=str(payload.canonical_url) if payload.canonical_url else None,
        confidence=payload.confidence, metadata_json=payload.metadata,
    )
    if payload.external_id:
        existing = session.scalar(select(MarketEvent).where(
            MarketEvent.source_key == payload.source_key,
            MarketEvent.external_id == payload.external_id,
        ))
        if existing:
            for field in ("title", "summary", "event_type", "status", "event_date", "published_at", "canonical_url", "confidence", "metadata_json"):
                setattr(existing, field, getattr(event, field))
            session.commit()
            session.refresh(existing)
            return existing
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def create_social_post(session: Session, payload: Any) -> SocialPost:
    source = session.get(DataSource, payload.source_key)
    if source is None or not source.enabled:
        raise ValueError("Social source is not registered and enabled. Enable it only after API/terms review.")
    if payload.related_entity_id and session.get(ResearchEntity, payload.related_entity_id) is None:
        raise ValueError("Unknown related_entity_id.")
    if payload.expires_at <= datetime.now(timezone.utc):
        raise ValueError("Social post expiry must be in the future.")
    row = session.scalar(select(SocialPost).where(
        SocialPost.source_key == payload.source_key, SocialPost.external_id == payload.external_id
    ))
    values = {
        "related_entity_id": payload.related_entity_id,
        "canonical_url": str(payload.canonical_url) if payload.canonical_url else None,
        "text_excerpt": None, "content_hash": payload.content_hash,
        "published_at": payload.published_at, "engagement_count": payload.engagement_count,
        "sentiment_label": payload.sentiment_label, "sentiment_score": payload.sentiment_score,
        "sentiment_model": payload.sentiment_model, "is_spam": payload.is_spam,
        "expires_at": payload.expires_at, "metadata_json": payload.metadata,
    }
    if row is None:
        row = SocialPost(source_key=payload.source_key, external_id=payload.external_id, **values)
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    session.commit()
    session.refresh(row)
    return row


def social_analytics(session: Session, entity_id: int | None, start: date | None, end: date | None) -> dict[str, Any]:
    stmt = select(SocialPost).where(SocialPost.is_spam.is_(False)).where(
        (SocialPost.expires_at.is_(None)) | (SocialPost.expires_at > datetime.now(timezone.utc))
    )
    if entity_id:
        stmt = stmt.where(SocialPost.related_entity_id == entity_id)
    if start:
        stmt = stmt.where(func.date(SocialPost.published_at) >= start)
    if end:
        stmt = stmt.where(func.date(SocialPost.published_at) <= end)
    rows = session.scalars(stmt.order_by(SocialPost.published_at)).all()
    distribution = {"positive": 0, "neutral": 0, "negative": 0}
    total_score = D("0")
    scored = 0
    daily: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.sentiment_label:
            distribution[row.sentiment_label] += 1
        if row.sentiment_score is not None:
            total_score += row.sentiment_score
            scored += 1
        if row.published_at:
            daily[row.published_at.date().isoformat()] += 1
    return {
        "from_date": start, "to_date": end, "post_count": len(rows),
        "coverage_entity_count": len({r.related_entity_id for r in rows if r.related_entity_id}),
        "average_sentiment": total_score / scored if scored else None,
        "sentiment_distribution": distribution,
        "discussion_volume_by_day": [{"date": k, "count": v} for k, v in sorted(daily.items())],
    }


def extract_pdf_text(content: bytes) -> tuple[str, int]:
    """Extract embedded PDF text and reject malformed, encrypted, or scanned documents."""
    import fitz

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF is malformed or cannot be opened.") from exc
    try:
        if document.is_encrypted or document.needs_pass:
            raise ValueError("Password-protected PDFs are not supported.")
        if document.page_count < 1:
            raise ValueError("PDF contains no pages.")
        pages = [page.get_text("text").strip() for page in document]
        text = "\n\n".join(
            f"[Page {index + 1}]\n{value}"
            for index, value in enumerate(pages)
            if value
        )
        if len(text.strip()) < 80:
            raise ValueError(
                "PDF has no usable embedded text; OCR is required for scanned documents."
            )
        return text, len(document)
    finally:
        document.close()


def split_document(text: str, chunk_size: int = 1200, overlap: int = 180) -> list[str]:
    """Create stable overlapping chunks while retaining page markers in extracted text."""
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not normalized:
        return []
    chunks, start = [], 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind("\n", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def store_document(
    session: Session, *, source_key: str, title: str, media_type: str,
    content: bytes, extracted_text: str, page_count: int,
    scheme_code: int | None = None, related_entity_id: int | None = None,
    published_at: datetime | None = None, effective_date: date | None = None,
    canonical_url: str | None = None, original_filename: str | None = None,
) -> ResearchDocument:
    source = session.get(DataSource, source_key)
    if source is None or not source.enabled:
        raise ValueError("Unknown or disabled document source.")
    if scheme_code and session.get(MutualFundScheme, scheme_code) is None:
        raise ValueError("Unknown scheme_code.")
    if related_entity_id and session.get(ResearchEntity, related_entity_id) is None:
        raise ValueError("Unknown related_entity_id.")
    digest = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(ResearchDocument).where(
        ResearchDocument.source_key == source_key, ResearchDocument.content_hash == digest
    ))
    if existing:
        return existing
    evidence_external_id = "document:" + digest
    evidence = session.scalar(select(EvidenceRecord).where(
        EvidenceRecord.source_key == source_key,
        EvidenceRecord.external_id == evidence_external_id,
    ))
    if evidence is None:
        evidence = EvidenceRecord(
            source_key=source_key, external_id=evidence_external_id,
            canonical_url=canonical_url, title=title, published_at=published_at,
            effective_from=effective_date, content_hash=digest,
            verification_status="unverified",
            metadata_json={"media_type": media_type, "original_filename": original_filename},
        )
        session.add(evidence)
        session.flush()
    document = ResearchDocument(
        source_key=source_key, scheme_code=scheme_code, related_entity_id=related_entity_id,
        evidence_id=evidence.evidence_id, title=title, original_filename=original_filename,
        media_type=media_type, canonical_url=canonical_url, content_hash=digest,
        published_at=published_at, effective_date=effective_date,
        extracted_text=extracted_text, page_count=page_count,
    )
    session.add(document)
    session.flush()
    chunk_rows = []
    for index, chunk in enumerate(split_document(extracted_text)):
        page_match = re.search(r"\[Page (\d+)\]", chunk)
        page_number = int(page_match.group(1)) if page_match else None
        chunk_rows.append({
            "text": chunk, "chunk_index": index, "page_number": page_number,
            "scheme_code": scheme_code, "content_hash": digest, "source_key": source_key,
        })
        session.add(DocumentChunk(
            document_id=document.document_id, chunk_index=index, page_number=page_number,
            chunk_text=chunk, token_estimate=max(1, len(chunk) // 4),
            metadata_json={"source_title": title, "content_hash": digest},
        ))
    session.commit()
    session.refresh(document)
    from mutual_fund_agent_analysis.data.services.document_vectors import index_chunks
    index_chunks(document.document_id, title, chunk_rows)
    return document


def search_documents(session: Session, query: str, scheme_code: int | None, limit: int = 8) -> dict[str, Any]:
    terms = [term for term in re.findall(r"[a-zA-Z0-9]{3,}", query.lower())[:12]]
    if not terms:
        raise ValueError("Query must contain at least one searchable term.")
    from mutual_fund_agent_analysis.data.services.document_vectors import search_chunks
    semantic = search_chunks(query, limit, scheme_code)
    if semantic is not None:
        return {"query": query, "results": semantic, "retrieval_mode": "qdrant_semantic"}
    stmt = select(DocumentChunk, ResearchDocument).join(
        ResearchDocument, ResearchDocument.document_id == DocumentChunk.document_id
    )
    if scheme_code:
        stmt = stmt.where(ResearchDocument.scheme_code == scheme_code)
    conditions = [func.lower(DocumentChunk.chunk_text).contains(term) for term in terms]
    from sqlalchemy import or_
    stmt = stmt.where(or_(*conditions))
    rows = session.execute(stmt.limit(min(max(limit * 4, limit), 100))).all()
    scored = []
    for chunk, doc in rows:
        haystack = chunk.chunk_text.lower()
        score = sum(haystack.count(term) for term in terms)
        scored.append((score, chunk, doc))
    scored.sort(key=lambda item: (item[0], item[1].chunk_id), reverse=True)
    results = [{
        "score": score, "document_id": doc.document_id, "title": doc.title,
        "source_key": doc.source_key, "content_hash": doc.content_hash,
        "effective_date": doc.effective_date, "published_at": doc.published_at,
        "page_number": chunk.page_number, "chunk_index": chunk.chunk_index,
        "text": chunk.chunk_text,
        "citation": {"document_id": doc.document_id, "chunk_id": chunk.chunk_id,
                     "title": doc.title, "content_hash": doc.content_hash},
    } for score, chunk, doc in scored[:limit]]
    return {"query": query, "results": results, "retrieval_mode": "lexical_fallback"}


def source_social_retention_days(source: DataSource, default_days: int) -> int:
    """Resolve a source-specific retention override with a bounded global fallback."""
    if source.source_type != "social":
        raise ValueError("Social retention can only be configured for a social data source.")
    if type(default_days) is not int or not 1 <= default_days <= 365:
        raise ValueError("Default social retention must be an integer between 1 and 365 days.")
    metadata = source.metadata_json or {}
    if not isinstance(metadata, dict):
        raise ValueError("Data source metadata must be a JSON object.")
    configured = metadata.get("retention_days")
    if configured is None:
        return default_days
    if type(configured) is not int or not 1 <= configured <= 365:
        raise ValueError(
            "Data source metadata.retention_days must be an integer between 1 and 365 days."
        )
    return configured


def purge_expired_social_posts(session: Session) -> int:
    """Delete expired social identifiers and derived metadata according to provider retention."""
    result = session.execute(
        delete(SocialPost).where(
            SocialPost.expires_at.is_not(None),
            SocialPost.expires_at <= datetime.now(timezone.utc),
        )
    )
    session.commit()
    return int(result.rowcount or 0)


def fund_social_sentiment(
    session: Session, scheme_code: int, start: date, end: date
) -> dict[str, Any]:
    """Aggregate scored company discussion against holdings effective at each post date."""
    snapshots = session.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.scheme_code == scheme_code)
        .where(PortfolioSnapshot.effective_date <= end)
        .order_by(PortfolioSnapshot.effective_date, PortfolioSnapshot.snapshot_id)
    ).all()
    if not snapshots:
        raise ValueError("No portfolio snapshots are available in the requested period.")
    posts = session.scalars(
        select(SocialPost)
        .where(SocialPost.related_entity_id.is_not(None))
        .where(SocialPost.sentiment_score.is_not(None))
        .where(SocialPost.is_spam.is_(False))
        .where(SocialPost.published_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
        .where(SocialPost.published_at < datetime.combine(end, datetime.max.time(), timezone.utc))
        .where((SocialPost.expires_at.is_(None)) | (SocialPost.expires_at > datetime.now(timezone.utc)))
        .order_by(SocialPost.published_at)
    ).all()
    total_weight_days = D("0")
    covered_weight_days = D("0")
    sentiment_weight_days = D("0")
    intervals = []
    for index, snapshot in enumerate(snapshots):
        interval_start = max(start, snapshot.effective_date)
        interval_end = min(
            end,
            snapshots[index + 1].effective_date - date.resolution
            if index + 1 < len(snapshots) else end,
        )
        if interval_start > interval_end:
            continue
        days = D((interval_end - interval_start).days + 1)
        holdings = session.scalars(select(PortfolioHolding).where(
            PortfolioHolding.snapshot_id == snapshot.snapshot_id
        )).all()
        weight_by_entity: dict[int, Decimal] = defaultdict(lambda: D("0"))
        for row in holdings:
            if row.company_entity_id is not None and row.weight_pct is not None:
                weight_by_entity[row.company_entity_id] += row.weight_pct
        total_weight = sum((row.weight_pct or D("0") for row in holdings), D("0"))
        total_weight_days += total_weight * days
        relevant = [
            post for post in posts
            if post.published_at and interval_start <= post.published_at.date() <= interval_end
            and post.related_entity_id in weight_by_entity
        ]
        grouped: dict[int, list[Decimal]] = defaultdict(list)
        for post in relevant:
            grouped[post.related_entity_id].append(post.sentiment_score)
        interval_covered = D("0")
        interval_score = D("0")
        for entity_id, scores in grouped.items():
            weight = weight_by_entity[entity_id]
            average = sum(scores, D("0")) / len(scores)
            interval_covered += weight
            interval_score += weight * average
        covered_weight_days += interval_covered * days
        sentiment_weight_days += interval_score * days
        intervals.append({
            "snapshot_id": snapshot.snapshot_id,
            "effective_date": snapshot.effective_date,
            "period_start": interval_start,
            "period_end": interval_end,
            "scored_company_count": len(grouped),
            "post_count": len(relevant),
            "coverage_weight_pct": interval_covered,
        })
    return {
        "scheme_code": scheme_code, "start_date": start, "end_date": end,
        "weighted_sentiment": sentiment_weight_days / covered_weight_days if covered_weight_days else None,
        "coverage_pct": (covered_weight_days / total_weight_days * D("100")) if total_weight_days else D("0"),
        "covered_weight_days": covered_weight_days,
        "total_weight_days": total_weight_days,
        "intervals": intervals,
        "coverage_start_date": max(start, snapshots[0].effective_date),
        "method": "time-weighted company sentiment using disclosure-effective portfolio weights",
        "warning": "Experimental discussion indicator; it is not a NAV, return, or investment recommendation.",
    }


def events_for_fund_exposure(
    session: Session, scheme_code: int, start: date | None, end: date | None, limit: int = 100
) -> dict[str, Any]:
    """Map company/sector events to the fund holdings snapshot effective on the event date."""
    entity_filter = select(MarketEvent).where(MarketEvent.related_entity_id.is_not(None))
    if start:
        entity_filter = entity_filter.where(MarketEvent.event_date >= start)
    if end:
        entity_filter = entity_filter.where(MarketEvent.event_date <= end)
    events = session.scalars(
        entity_filter.order_by(MarketEvent.event_date.desc().nullslast()).limit(limit)
    ).all()
    mapped = []
    for event in events:
        if event.event_date is None:
            mapped.append({"event_id": event.event_id, "title": event.title,
                           "status": event.status, "exposure_found": False,
                           "reason": "Event has no effective event date."})
            continue
        snapshot = latest_snapshot(session, scheme_code, event.event_date)
        if snapshot is None:
            mapped.append({"event_id": event.event_id, "title": event.title,
                           "status": event.status, "exposure_found": False,
                           "reason": "No portfolio disclosure effective on or before the event date."})
            continue
        entity = session.get(ResearchEntity, event.related_entity_id)
        holdings = session.scalars(select(PortfolioHolding).where(
            PortfolioHolding.snapshot_id == snapshot.snapshot_id
        )).all()
        matches = []
        for holding in holdings:
            matched = holding.company_entity_id == event.related_entity_id
            if entity and entity.entity_type == "sector" and holding.sector:
                matched = holding.sector.strip().casefold() == entity.canonical_name.strip().casefold()
            if matched:
                matches.append({
                    "security_key": holding.security_key,
                    "security_name": holding.security_name,
                    "sector": holding.sector,
                    "weight_pct": holding.weight_pct,
                })
        mapped.append({
            "event_id": event.event_id, "title": event.title,
            "event_type": event.event_type, "status": event.status,
            "event_date": event.event_date, "source_key": event.source_key,
            "evidence_id": event.evidence_id, "canonical_url": event.canonical_url,
            "portfolio_effective_date": snapshot.effective_date,
            "exposure_found": bool(matches), "holdings": matches,
            "aggregate_exposure_pct": sum((item["weight_pct"] or D("0") for item in matches), D("0")),
        })
    return {"scheme_code": scheme_code, "count": len(mapped), "events": mapped}
