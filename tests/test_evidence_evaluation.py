from mutual_fund_agent_analysis.evaluation.runner import evaluate_evidence_cases


def test_evidence_dataset_checks_positive_and_negative_contract_cases():
    result = evaluate_evidence_cases(
        [
            {
                "name": "good",
                "expected_pass": True,
                "response": {
                    "results": {"fund": {}},
                    "citations": [
                        {
                            "source_key": "official",
                            "canonical_url": "https://example.com/source",
                            "retrieved_at": "2026-11-25T10:00:00+00:00",
                            "verification_status": "verified",
                        }
                    ],
                },
            },
            {
                "name": "missing_source",
                "expected_pass": False,
                "response": {"results": {"fund": {}}, "citations": [{}]},
            },
        ]
    )
    assert result["accuracy"] == 1.0
    assert result["case_count"] == 2
