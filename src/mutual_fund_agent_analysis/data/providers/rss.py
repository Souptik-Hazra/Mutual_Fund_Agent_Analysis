"""Allowlisted RSS/Atom ingestion adapter for official event feeds."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx


MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_FEED_ITEMS = 250
USER_AGENT = "MutualFundResearch/1.0"


def _safe_https_url(value: str, *, allowed_host: str | None = None) -> bool:
    parsed = urlparse(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
        and not parsed.fragment
        and (allowed_host is None or parsed.hostname.casefold() == allowed_host.casefold())
    )


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_event_date(node: ElementTree.Element) -> date | None:
    """Read an explicitly supplied effective/event date; never substitute publication date."""
    candidates = (
        "eventDate",
        "effectiveDate",
        "event_date",
        "effective_date",
        "{https://www.nseindia.com/rss}eventDate",
    )
    for tag in candidates:
        element = node.find(tag)
        value = (element.text or "").strip() if element is not None else ""
        if not value:
            continue
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            parsed = _parse_datetime(value)
            if parsed:
                return parsed.date()
    return None


def fetch_feed(url: str, allowed_host: str) -> list[dict[str, Any]]:
    """Fetch one explicitly allowlisted HTTPS feed without following redirects."""
    if not _safe_https_url(url, allowed_host=allowed_host):
        raise ValueError("Feed URL must use HTTPS on the registered source host without credentials or a nonstandard port.")
    with httpx.Client(
        timeout=httpx.Timeout(20.0, connect=5.0),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        if len(response.content) > MAX_FEED_BYTES:
            raise ValueError("RSS/Atom feed exceeds the 5 MB response limit.")
        if response.status_code != 200:
            raise ValueError("RSS/Atom feed returned an unexpected status.")
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as exc:
        raise ValueError("RSS/Atom feed contains malformed XML.") from exc

    nodes = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
    items: list[dict[str, Any]] = []
    for node in nodes[:MAX_FEED_ITEMS]:
        def value(tag: str, atom_tag: str | None = None) -> str:
            element = node.find(tag)
            if element is None and atom_tag:
                element = node.find(atom_tag)
            return (element.text or "").strip() if element is not None else ""

        title = value("title", "{http://www.w3.org/2005/Atom}title")
        link = value("link")
        if not link:
            link_node = node.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.attrib.get("href", "") if link_node is not None else ""
        if not _safe_https_url(link):
            continue
        guid = value("guid", "{http://www.w3.org/2005/Atom}id") or link or title
        summary = value("description", "{http://www.w3.org/2005/Atom}summary")
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\\s+", " ", summary).strip()
        published = value("pubDate", "{http://www.w3.org/2005/Atom}published") or value(
            "{http://www.w3.org/2005/Atom}updated"
        )
        if title:
            items.append({
                "external_id": hashlib.sha256(guid.encode("utf-8")).hexdigest(),
                "title": title[:500],
                "summary": summary[:4000],
                "url": link[:1000],
                "published_at": _parse_datetime(published),
                "event_date": _parse_event_date(node),
            })
    return items
