"""Purge social records whose provider retention expiry has passed."""
# ruff: noqa: E501
from mutual_fund_agent_analysis.data.services.research_intelligence import (\n    purge_expired_social_posts,\n)
from mutual_fund_agent_analysis.database.session import get_session_factory


def main() -> None:
    with get_session_factory()() as session:
        deleted = purge_expired_social_posts(session)
    print(f"Purged {deleted} expired social records.")


if __name__ == "__main__":
    main()
