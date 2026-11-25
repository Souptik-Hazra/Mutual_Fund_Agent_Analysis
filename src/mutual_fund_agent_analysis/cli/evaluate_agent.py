"""Run the offline research assistant routing evaluation suite."""

import json
from pathlib import Path

from mutual_fund_agent_analysis.evaluation.runner import load_and_evaluate


def main() -> None:
    dataset = Path("evaluation/research-routing.json")
    result = load_and_evaluate(dataset)
    print(json.dumps(result, indent=2))
    if result["exact_match_accuracy"] < 0.90:
        raise SystemExit("Routing evaluation below 90% exact-match accuracy.")


if __name__ == "__main__":
    main()
