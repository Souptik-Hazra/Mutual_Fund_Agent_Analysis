"""Official API clients for permitted Reddit and X data collection."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from mutual_fund_agent_analysis.core.config import get_settings


class SocialProviderError(RuntimeError):
    """Raised when an official social API is unavailable or credentials are missing."""


def search_reddit(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search Reddit through OAuth; requires an approved app and enabled source registry row."""
    settings = get_settings()
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        raise SocialProviderError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required.")
    client_id = settings.reddit_client_id.get_secret_value()
    secret = settings.reddit_client_secret.get_secret_value()
    token_url = "https://www.reddit.com/api/v1/access_token"
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode(),
        "User-Agent": settings.reddit_user_agent,
    }
    with httpx.Client(timeout=20) as client:
        token_response = client.post(token_url, data={"grant_type": "client_credentials"}, headers=headers)
        token_response.raise_for_status()
        token = token_response.json().get("access_token")
        if not token:
            raise SocialProviderError("Reddit OAuth response did not contain an access token.")
        response = client.get(
            "https://oauth.reddit.com/search",
            params={"q": query, "sort": "new", "limit": min(max(limit, 1), 100), "t": "month", "raw_json": 1},
            headers={"Authorization": f"Bearer {token}", "User-Agent": settings.reddit_user_agent},
        )
        response.raise_for_status()
    children = response.json().get("data", {}).get("children", [])
    rows = []
    for item in children:
        data = item.get("data", {})
        created = data.get("created_utc")
        rows.append({
            "external_id": str(data.get("id")),
            "text_excerpt": (data.get("title", "") + " " + data.get("selftext", ""))[:2000],
            "canonical_url": "https://www.reddit.com" + data.get("permalink", ""),
            "published_at": datetime.fromtimestamp(created, tz=timezone.utc) if created else None,
            "engagement_count": int(data.get("score", 0)) + int(data.get("num_comments", 0)),
            "metadata": {"subreddit": data.get("subreddit"), "kind": "reddit_submission"},
        })
    return rows


def search_x(query: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search recent public posts through X API v2; API access is plan/permission dependent."""
    settings = get_settings()
    if not settings.x_bearer_token:
        raise SocialProviderError("X_BEARER_TOKEN is required.")
    with httpx.Client(timeout=20) as client:
        response = client.get(
            "https://api.x.com/2/tweets/search/recent",
            params={
                "query": query + " -is:retweet",
                "max_results": min(max(limit, 10), 100),
                "tweet.fields": "created_at,public_metrics,lang",
            },
            headers={"Authorization": f"Bearer {settings.x_bearer_token.get_secret_value()}"},
        )
        response.raise_for_status()
    rows = []
    for item in response.json().get("data", []):
        metrics = item.get("public_metrics", {})
        rows.append({
            "external_id": item["id"],
            "text_excerpt": item.get("text", "")[:2000],
            "canonical_url": f"https://x.com/i/web/status/{item['id']}",
            "published_at": datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                if item.get("created_at") else None,
            "engagement_count": sum(int(metrics.get(k, 0)) for k in
                                    ("like_count", "reply_count", "retweet_count", "quote_count")),
            "metadata": {"lang": item.get("lang"), "public_metrics": metrics},
        })
    return rows


def social_provider_credentials() -> dict[str, bool]:
    """Return credential readiness only; never expose configured secret values."""
    settings = get_settings()
    return {
        "reddit": bool(
            settings.reddit_client_id
            and settings.reddit_client_id.get_secret_value().strip()
            and settings.reddit_client_secret
            and settings.reddit_client_secret.get_secret_value().strip()
        ),
        "x": bool(settings.x_bearer_token and settings.x_bearer_token.get_secret_value().strip()),
    }
