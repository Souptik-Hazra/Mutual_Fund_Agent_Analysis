# Personal agent evaluation

`research-routing.json` is a small deterministic routing benchmark. Run `mfa-evaluate-agent` from the repository root after installing the `agents` extra. It checks specialist selection without API keys, external calls or database fixtures. Exact-match accuracy is the main score; per-intent precision and recall show which specialist routing needs improvement. Extend the dataset with reviewed examples before tuning routing rules.
