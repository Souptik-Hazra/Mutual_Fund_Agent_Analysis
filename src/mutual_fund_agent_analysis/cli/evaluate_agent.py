"""Run the offline research routing and evidence-contract evaluations."""

import json
from pathlib import Path

from mutual_fund_agent_analysis.evaluation.runner import (
    load_and_evaluate,
    load_and_evaluate_evidence,
)


def main() -> None:
    routing = load_and_evaluate(Path("evaluation/research-routing.json"))
    evidence = load_and_evaluate_evidence(Path("evaluation/research-evidence.json"))
    print(json.dumps({"routing": routing, "evidence": evidence}, indent=2))
    if routing["exact_match_accuracy"] < 0.90:
        raise SystemExit("Routing evaluation below 90% exact-match accuracy.")
    if evidence["accuracy"] < 1.0:
        raise SystemExit("Evidence-contract evaluation contains regressions.")


if __name__ == "__main__":
    main()
