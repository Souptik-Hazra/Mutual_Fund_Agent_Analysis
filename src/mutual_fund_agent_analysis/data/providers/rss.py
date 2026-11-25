"""Allowlisted RSS/Atom ingestion adapter for official event feeds."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx


def fetch_feed(url: str, allowed_host: str) -> list[dict[str, Any]]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != allowed_host:
        raise ValueError("Feed URL must use HTTPS and the registered source host.")
    with httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": "MutualFundResearch/1.0"}) as client:
        response = client.get(url)
        response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    items = []
    for node in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
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
        guid = value("guid", "{http://www.w3.org/2005/Atom}id") or link or title
        summary = value("description", "{http://www.w3.org/2005/Atom}summary")
        summary = re.sub(r"<[^>]+>", " ", summary)
        published = value("pubDate", "{http://www.w3.org/2005/Atom}published") or value(
            "{http://www.w3.org/2005/Atom}updated"
        )
        published_at = None
        if published:
            try:
                published_at = parsedate_to_datetime(published)
            except (TypeError, ValueError):
                try:
                    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    published_at = None
        if published_at and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        if title and link:
            items.append({
                "external_id": hashlib.sha256(guid.encode("utf-8")).hexdigest(),
                "title": title[:500], "summary": summary[:4000], "url": link[:1000],
                "published_at": published_at,
            })
    return items
