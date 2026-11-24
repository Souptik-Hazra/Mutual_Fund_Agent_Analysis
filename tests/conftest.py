"""Shared test fixtures."""
import pytest
from fastapi.testclient import TestClient

from mutual_fund_agent_analysis.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create an isolated API test client."""
    return TestClient(create_app())
