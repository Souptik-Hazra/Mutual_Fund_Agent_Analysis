from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mutual_fund_agent_analysis.cli.register_source import register_data_source
from mutual_fund_agent_analysis.database.base import Base
from mutual_fund_agent_analysis.models import DataSource


def test_register_data_source_creates_and_updates_distinct_amc_registry_entries():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as session:
            first = register_data_source(
                session,
                source_key="hdfc_amc",
                display_name="HDFC Mutual Fund",
                source_type="official",
                authority_tier=1,
                is_official=True,
                enabled=True,
                base_url="https://www.hdfcfund.com",
                terms_url="https://www.hdfcfund.com/terms",
                attribution_required=False,
                metadata={"domain": "idcw", "reviewed": True},
            )
            assert first.base_url == "https://www.hdfcfund.com/"
            assert first.enabled is True
            assert first.is_official is True

            updated = register_data_source(
                session,
                source_key="hdfc_amc",
                display_name="HDFC Mutual Fund",
                source_type="official",
                authority_tier=1,
                is_official=True,
                enabled=False,
                base_url="https://www.hdfcfund.com",
            )
            assert updated.source_key == first.source_key
            assert updated.enabled is False
            assert updated.terms_url is None
            assert session.query(DataSource).count() == 1
    finally:
        engine.dispose()


def test_register_data_source_rejects_unsafe_urls_and_authority_mismatch():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        with factory() as session:
            args = {
                "source_key": "bad_source",
                "display_name": "Bad Source",
                "source_type": "provider",
                "authority_tier": 2,
                "is_official": False,
                "enabled": False,
                "base_url": "https://user:password@example.com",
            }
            import pytest

            with pytest.raises(ValueError, match="base_url"):
                register_data_source(session, **args)
            args["base_url"] = "https://example.com"
            args["is_official"] = True
            with pytest.raises(ValueError, match="source_type"):
                register_data_source(session, **args)
    finally:
        engine.dispose()
