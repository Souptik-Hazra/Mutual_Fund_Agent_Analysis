from mutual_fund_agent_analysis.main import create_app


def test_financial_reliability_routes_are_registered():
    paths = create_app().openapi()["paths"]
    assert "/api/v1/audit/coverage" in paths
    assert "/api/v1/schemes/{scheme_code}/metadata-observations" in paths
    assert "/api/v1/schemes/{scheme_code}/distributions" in paths
    assert "/api/v1/schemes/{scheme_code}/distribution-coverage" in paths
    assert "/api/v1/schemes/{scheme_code}/idcw-total-return" in paths
    assert "/api/v1/portfolios/{scheme_code}/quality" in paths


def test_analytics_contract_exposes_all_sampling_frequencies():
    paths = create_app().openapi()["paths"]
    parameters = paths["/api/v1/schemes/{scheme_code}/analytics"]["get"]["parameters"]
    frequency = next(item for item in parameters if item["name"] == "frequency")
    assert frequency["schema"]["enum"] == [
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "yearly",
    ]


def test_metadata_quality_route_is_registered():
    paths = create_app().openapi()["paths"]
    assert "/api/v1/schemes/{scheme_code}/metadata-quality" in paths


def test_metadata_quality_and_idcw_payout_contracts_are_registered():
    paths = create_app().openapi()["paths"]
    assert "/api/v1/schemes/{scheme_code}/metadata-quality" in paths
    components = create_app().openapi()["components"]["schemas"]
    assert components["IDCWTotalReturnResponse"]["properties"]["return_basis"]["enum"] == [
        "idcw_payout_total_return",
        "idcw_reinvested_total_return",
    ]


def test_event_revision_history_route_is_registered():
    paths = create_app().openapi()["paths"]
    assert "/api/v1/events/{event_id}/revisions" in paths


def test_event_listing_exposes_timezone_aware_historical_as_of_filter():
    parameters = create_app().openapi()["paths"]["/api/v1/events"]["get"]["parameters"]
    as_of = next(item for item in parameters if item["name"] == "as_of")
    assert as_of["schema"]["type"] == "string"
    assert as_of["schema"]["format"] == "date-time"


def test_document_delete_route_is_registered():
    paths = create_app().openapi()["paths"]
    assert "delete" in paths["/api/v1/documents/{document_id}"]
